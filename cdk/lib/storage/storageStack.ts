/**
 * Storage infrastructure stack for NovaAct human intervention workflows.
 *
 * @remarks
 * This stack provides the foundational data storage and content delivery infrastructure:
 *
 * **DynamoDB Tables:**
 * - Connections table: Tracks active WebSocket connections with TTL-based cleanup
 * - Executions table: Stores workflow execution state with DynamoDB Streams for SPA cleanup
 *
 * **S3 Storage:**
 * - SPA bucket: Hosts dynamically-generated single-page applications for user interactions
 * - Lifecycle rules: Automatic cleanup of temporary SPA files after 24 hours
 * - Error pages: Pre-deployed HTML pages for expired sessions and server errors
 *
 * **CloudFront Distribution:**
 * - Provides low-latency, secure access to SPA content
 * - Custom error responses for 403/404/500/503 status codes
 * - Origin Access Identity for private S3 access
 *
 * **Security:**
 * - DynamoDB: AWS-managed encryption at rest
 * - S3: S3-managed encryption (compatible with CloudFront)
 * - CloudFront: HTTPS-only with redirect from HTTP
 *
 * @packageDocumentation
 */
import { Stack, StackProps } from 'aws-cdk-lib';
import { RemovalPolicy, Duration, SecretValue } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Table, AttributeType, BillingMode, TableEncryption, StreamViewType } from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { NotificationChannel, UseCase } from '../models';

/**
 * Configuration properties for the storage stack.
 *
 * @remarks
 * Controls deployment stage, environment, and resource naming for the storage infrastructure.
 */
interface StorageStackProps extends StackProps {
  /** AWS deployment environment (account and region) */
  
  /** Deployment stage name (alpha, beta, gamma, prod) */
  readonly stage: string;
  /** Production flag affecting retention policies and removal settings */
  readonly isProd: boolean;
  /** Optional disambiguator for multi-deployment scenarios (defaults to stage) */
  readonly disambiguator?: string;
  /** Notification channels for alerting users (EMAIL, SLACK) */
  readonly notificationChannels: NotificationChannel[];
}

/**
 * Storage stack providing DynamoDB tables, S3 buckets, and CloudFront distribution.
 *
 * @remarks
 * This stack is deployed first and its resources are shared across all workflow stacks
 * (Approval, UI Takeover, WebSocket Executor).
 *
 * **Resource Lifecycle:**
 * - Connections table: DESTROY on stack deletion (transient connection data)
 * - Executions table: RETAIN on stack deletion (audit trail preservation)
 * - SPA bucket: DESTROY on stack deletion (temporary files only)
 * - CloudFront: DESTROY on stack deletion (can be recreated)
 *
 * **DynamoDB Streams:**
 * The executions table has streams enabled to trigger Lambda functions when
 * TTL expires records, allowing automatic cleanup of SPA objects from S3.
 *
 * @example
 * ```typescript
 * const storage = new StorageStack(app, 'NovaActStorage', {
 *   env: { account: '123456789012', region: 'us-east-1' },
 *   stage: 'production',
 *   isProd: true,
 *   disambiguator: 'my-company',
 * });
 *
 * // Use in other stacks
 * const approvalStack = new ApprovalStepFunctionStack(app, 'Approval', {
 *   connectionsTable: storage.connectionsTable,
 *   executionsTable: storage.executionsTable,
 *   spaBucket: storage.spaBucket,
 *   cloudFrontDistribution: storage.cloudFrontDistribution,
 *   // ...
 * });
 * ```
 */
export class StorageStack extends Stack {
  /** DynamoDB table for WebSocket connection tracking with TTL */
  public readonly connectionsTable: Table;
  /** DynamoDB table for workflow execution state with Streams enabled */
  public readonly executionsTable: Table;
  /** S3 bucket for SPA assets and temporary file storage */
  public readonly spaBucket: s3.Bucket;
  /** CloudFront distribution for low-latency SPA delivery */
  public readonly cloudFrontDistribution: cloudfront.Distribution;
  /** Origin Access Identity for secure S3 access via CloudFront */
  public readonly originAccessIdentity: cloudfront.OriginAccessIdentity;
  /** Shared Secrets Manager secret for Slack bot token (if SLACK channel configured) */
  public readonly slackSecrets?: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: StorageStackProps) {
    super(scope, id, props);

    const disambiguator = props.disambiguator;

    /**
     * Set up shared Slack notification resources if SLACK channel is configured.
     * Creates a single Secrets Manager secret that all stacks (Approval, UI Takeover, WebSocket) will reference.
     *
     * @remarks
     * The secret is created with a JSON structure containing bot token fields for each use case:
     * ```json
     * {
     *   "UITakeover": "",
     *   "Approval": ""
     * }
     * ```
     *
     * After deployment, populate the secret with your Slack bot tokens:
     * - For a shared bot token across use cases: set both fields to the same token
     * - For separate bot tokens per use case: set each field to its respective token
     *
     * Example populated secret:
     * ```json
     * {
     *   "UITakeover": "xoxb-your-bot-token-here",
     *   "Approval": "xoxb-your-bot-token-here"
     * }
     * ```
     */
    if (props.notificationChannels.includes(NotificationChannel.SLACK)) {
      this.slackSecrets = new secretsmanager.Secret(this, `SharedSlackSecrets-${disambiguator}`, {
        secretName: `nova-act-slack-secrets-${disambiguator}`,
        description: 'Shared Slack bot token for NovaAct human intervention notifications',
        secretObjectValue: {
          [UseCase.UI_TAKEOVER]: SecretValue.unsafePlainText(''),
          [UseCase.APPROVAL]: SecretValue.unsafePlainText(''),
        },
      });
    }

    /** Table for tracking WebSocket connections */
    this.connectionsTable = new Table(this, `ConnectionsTable-${disambiguator}`, {
      tableName: `HITL-Connections-${disambiguator}`,
      partitionKey: { name: 'connectionId', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      encryption: TableEncryption.AWS_MANAGED, // Use AWS-managed encryption
      removalPolicy: RemovalPolicy.DESTROY,
    });

    /** Table for tracking workflow executions */
    this.executionsTable = new Table(this, `ExecutionsTable-${disambiguator}`, {
      tableName: `HITL-Executions-${disambiguator}`,
      partitionKey: { name: 'eventId', type: AttributeType.STRING },
      timeToLiveAttribute: 'ttl',
      encryption: TableEncryption.AWS_MANAGED, // Use AWS-managed encryption
      removalPolicy: RemovalPolicy.RETAIN,
      // Enable DynamoDB Streams to capture TTL deletions for cleanup of expired SPA objects
      // OLD_IMAGE provides the full item data before deletion, which contains the spa_url
      stream: StreamViewType.OLD_IMAGE,
    });

    /** Shared S3 bucket for SPA assets across all workflows */
    this.spaBucket = new s3.Bucket(this, `SpaBucket-${disambiguator}`, {
      bucketName: `nova-act-hitl-spa-assets-${this.account}-${disambiguator}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED, // Use S3-managed encryption for CloudFront compatibility
      removalPolicy: RemovalPolicy.DESTROY,
      lifecycleRules: [
        {
          id: 'DeleteTemporarySPAsAfter1Day',
          enabled: true,
          expiration: Duration.days(1),
          // Only delete objects tagged as temporary (SPA HTML files)
          // Objects without this tag (like error pages) will not be deleted
          tagFilters: { temporary: 'true' },
        },
      ],
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET],
          allowedOrigins: ['*'],
          allowedHeaders: ['*'],
        },
      ],
    });

    // Deploy error pages for expired requests and server errors
    // Note: Both pages are deployed in a single BucketDeployment to avoid conflicts
    new s3deploy.BucketDeployment(this, `DeployErrorPages-${disambiguator}`, {
      sources: [
        s3deploy.Source.data(
          'error-pages/expired.html',
          `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Request Session Expired - Nova Act</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            min-height: 100vh;
            background: #f5f5f7;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 16px;
            padding: 48px;
            max-width: 680px;
            width: 100%;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
            text-align: center;
        }

        .icon {
            width: 56px;
            height: 56px;
            background: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 24px auto;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .icon::before {
            content: "✨";
            font-size: 28px;
            background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        h1 {
            font-size: 28px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 16px;
            line-height: 1.3;
        }

        p {
            font-size: 16px;
            color: #4a4a4a;
            line-height: 1.6;
        }

        a {
            color: #0066cc;
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        @media (max-width: 768px) {
            .container {
                padding: 32px 24px;
            }

            h1 {
                font-size: 24px;
            }

            p {
                font-size: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon"></div>
        <h1>The Request Session has Expired</h1>
        <p>
            This request link has already expired. Please contact the sender for further
            instruction or visit
            <a href="http://nova.amazon.com/act" target="_blank">
                http://nova.amazon.com/act
            </a>
            for more information.
        </p>
    </div>
</body>
</html>`,
        ),
        s3deploy.Source.data(
          'error-pages/server-error.html',
          `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Temporarily Unavailable - Nova Act</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            min-height: 100vh;
            background: #f5f5f7;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 16px;
            padding: 48px;
            max-width: 680px;
            width: 100%;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
            text-align: center;
        }

        .icon {
            width: 56px;
            height: 56px;
            background: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 24px auto;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .icon::before {
            content: "⚠️";
            font-size: 28px;
        }

        h1 {
            font-size: 28px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 16px;
            line-height: 1.3;
        }

        p {
            font-size: 16px;
            color: #4a4a4a;
            line-height: 1.6;
            margin-bottom: 12px;
        }

        a {
            color: #0066cc;
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        @media (max-width: 768px) {
            .container {
                padding: 32px 24px;
            }

            h1 {
                font-size: 24px;
            }

            p {
                font-size: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon"></div>
        <h1>Service Temporarily Unavailable</h1>
        <p>
            We're experiencing technical difficulties. Please try again in a few moments.
        </p>
        <p>
            If the problem persists, please contact the sender for further instruction or visit
            <a href="http://nova.amazon.com/act" target="_blank">
                http://nova.amazon.com/act
            </a>
            for more information.
        </p>
    </div>
</body>
</html>`,
        ),
      ],
      destinationBucket: this.spaBucket,
    });

    // Create CloudFront Origin Access Identity for secure S3 access
    this.originAccessIdentity = new cloudfront.OriginAccessIdentity(this, `SpaOAI-${disambiguator}`, {
      comment: `OAI for SPA bucket - ${disambiguator}`,
    });

    // Grant CloudFront read access to SPA bucket
    this.spaBucket.grantRead(this.originAccessIdentity);

    // Create CloudFront distribution for SPA bucket
    this.cloudFrontDistribution = new cloudfront.Distribution(this, `SpaDistribution-${disambiguator}`, {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessIdentity(this.spaBucket, {
          originAccessIdentity: this.originAccessIdentity,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED, // SPA content is dynamic
      },
      errorResponses: [
        {
          httpStatus: 403,
          responseHttpStatus: 403,
          responsePagePath: '/error-pages/expired.html',
          ttl: Duration.minutes(5),
        },
        {
          httpStatus: 404,
          responseHttpStatus: 404,
          responsePagePath: '/error-pages/expired.html',
          ttl: Duration.minutes(5),
        },
        {
          httpStatus: 500,
          responseHttpStatus: 500,
          responsePagePath: '/error-pages/server-error.html',
          ttl: Duration.minutes(5),
        },
        {
          httpStatus: 503,
          responseHttpStatus: 503,
          responsePagePath: '/error-pages/server-error.html',
          ttl: Duration.minutes(5),
        },
      ],
      comment: `SPA Distribution - ${disambiguator}`,
    });
  }
}
