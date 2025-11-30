/**
 * Base class for Step Function workflow stacks with shared API and notification infrastructure.
 *
 * @remarks
 * This abstract class provides common functionality for all NovaAct workflow types:
 *
 * **REST API Infrastructure:**
 * - API Gateway REST API for SPA interactions
 * - Custom Lambda authorizer for token-based authentication
 * - CORS configuration for browser-based SPA access
 * - OPTIONS methods for CORS preflight requests
 *
 * **Notification Setup:**
 * - Secrets Manager integration for Slack webhooks
 * - SES permissions for email notifications
 * - Environment variable configuration for notification channels
 *
 * **Lambda Function Management:**
 * - Dedicated IAM roles per Lambda function (least privilege)
 * - Consistent environment variable injection
 * - Common configuration (runtime, memory, timeout)
 *
 * **Security Considerations:**
 * - Unauthenticated OPTIONS requests are safe (CORS spec requirement)
 * - Actual API methods require valid authorization tokens
 * - Tokens validated against DynamoDB executions table
 * - TTL enforcement prevents expired session access
 *
 * Subclasses must implement:
 * - `createStepFunctionFlow()`: Define workflow state machine
 * - `setupApiLambdas()`: Create use case-specific API endpoints
 *
 * @packageDocumentation
 */
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { IFunction } from 'aws-cdk-lib/aws-lambda';
import { Role, ServicePrincipal, ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { StateMachine } from 'aws-cdk-lib/aws-stepfunctions';
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { NotificationChannel, UseCase, CORS_HEADERS_STRING } from '../models';
import { createLambdaFunction } from '../utils/lambdaUtils';

/**
 * Base configuration properties shared by all Step Function workflow stacks.
 *
 * @remarks
 * These properties are common to Approval and UI Takeover workflows.
 * Use case-specific stacks extend this interface with additional properties.
 */
export interface BaseStepFunctionStackProps extends StackProps {
  /** AWS deployment environment (account and region) */
  
  /** Deployment stage name (alpha, beta, gamma, prod) */
  readonly stage: string;
  /** Production flag affecting monitoring and retention */
  readonly isProd: boolean;
  /** Notification channels for alerting users (EMAIL, SLACK) */
  readonly notificationChannels: NotificationChannel[];
  /** DynamoDB table for WebSocket connection tracking */
  readonly connectionsTable: Table;
  /** DynamoDB table for workflow execution state */
  readonly executionsTable: Table;
  /** S3 bucket for SPA asset storage */
  readonly spaBucket: s3.Bucket;
  /** Use case type (APPROVAL or UI_TAKEOVER) */
  readonly useCase: UseCase;
  /** Disambiguator for multi-deployment scenarios */
  readonly disambiguator: string;
  /** Shared Secrets Manager secret name for Slack bot token (if SLACK channel configured) */
  readonly slackSecretsName?: string;
}

/**
 * Abstract base class providing shared infrastructure for Step Function workflow stacks.
 *
 * @remarks
 * This class implements the Template Method pattern, defining the skeleton of
 * workflow stack creation while deferring specific implementations to subclasses.
 *
 * **Initialization Flow:**
 * 1. Setup notification resources (Slack secrets if configured)
 * 2. Create REST API with CORS support
 * 3. Setup API Lambda functions (use case-specific, implemented by subclass)
 * 4. Create Step Function workflow (use case-specific, implemented by subclass)
 *
 * **Protected Members:**
 * Subclasses have access to:
 * - `stage`: Deployment stage name
 * - `disambiguator`: Resource naming suffix
 * - `notificationChannels`: Configured notification methods
 * - `api`: REST API Gateway instance
 * - `spaBucket`: S3 bucket for SPA files
 * - `useCase`: Workflow type identifier
 * - `slackSecrets`: Secrets Manager secret for Slack (if configured)
 *
 * @example
 * ```typescript
 * export class ApprovalStepFunctionStack extends BaseStepFunctionStack {
 *   protected createStepFunctionFlow(props) {
 *     // Create approval-specific workflow
 *   }
 *
 *   protected setupApiLambdas(props) {
 *     // Create approval-specific API endpoints
 *   }
 * }
 * ```
 */
export abstract class BaseStepFunctionStack extends Stack {
  /** Deployment stage name (alpha, beta, gamma, prod) */
  protected readonly stage: string;
  /** Resource naming disambiguator for multi-deployment support */
  protected readonly disambiguator: string;
  /** Configured notification channels for user alerts */
  protected readonly notificationChannels: NotificationChannel[];
  /** REST API Gateway for SPA interactions */
  protected readonly api: apigateway.RestApi;
  /** S3 bucket for SPA asset storage */
  protected readonly spaBucket: s3.Bucket;
  /** Use case identifier (APPROVAL or UI_TAKEOVER) */
  protected readonly useCase: UseCase;
  /** Secrets Manager secret name for Slack bot token (if SLACK channel configured) */
  protected slackSecretsName?: string;

  protected constructor(scope: Construct, id: string, props: BaseStepFunctionStackProps) {
    super(scope, id, props);
    this.useCase = props.useCase;
    this.stage = props.stage;
    this.disambiguator = props.disambiguator;
    this.notificationChannels = props.notificationChannels;
    this.spaBucket = props.spaBucket;
    this.slackSecretsName = props.slackSecretsName;
    this.api = this.createApi();
    this.setupApiLambdas(props);
  }

  /**
   * Create REST API with CORS and IAM authorization
   *
   * Security: Uses AWS SigV4 signing for requests from browser SPA
   * - Temporary AWS credentials embedded in presigned API requests
   * - SigV4 signatures validate request authenticity and prevent tampering
   * - Time-limited credentials (typically 1-24 hours) tied to specific workflows
   *
   * CORS Configuration:
   * - OPTIONS methods are added explicitly in setupApiLambdas() to avoid conflicts
   * - This is critical: browsers send unauthenticated OPTIONS preflight requests before actual requests
   * - If OPTIONS required auth, the preflight would fail with 403 before the actual request is sent
   * - IAM authorization is applied only to actual API methods (POST/GET) via explicit methodOptions
   * - Never use defaultMethodOptions with authorizationType, as it would apply auth to OPTIONS methods
   * - We don't use defaultCorsPreflightOptions because it conflicts with explicit OPTIONS methods
   *
   * Security of Unauthenticated OPTIONS Requests:
   * There are NO significant security risks with unauthenticated OPTIONS preflight requests:
   *
   * 1. OPTIONS requests don't execute business logic
   *    - API Gateway responds directly - Lambda functions never execute
   *    - No data is accessed, modified, or returned
   *    - Only returns metadata about allowed HTTP methods/headers
   *
   * 2. Minimal information disclosure
   *    - Only reveals: "This endpoint exists and accepts POST with these headers"
   *    - Attackers can discover this through trial-and-error anyway
   *    - Not materially different from public API documentation
   *
   * 3. Required by CORS specification (RFC 7231)
   *    - Browsers send OPTIONS BEFORE the actual request to check permissions
   *    - Browser hasn't attached auth headers yet - it's asking "am I allowed to?"
   *    - If OPTIONS required auth, it creates a chicken-and-egg problem
   *
   * 4. Industry standard practice
   *    - Every public API with CORS (AWS, Google Cloud, Azure, Stripe) uses unauthenticated OPTIONS
   *    - It's the only way CORS works with authenticated APIs
   *    - Actual API methods remain protected by IAM/SigV4, which is what matters for security
   *
   * Potential concerns (minimal):
   * - DDoS/Rate limiting: Mitigated by API Gateway throttling, CloudFront/WAF
   * - Same risk level as any public endpoint (even authentication endpoints must be public)
   */
  private createApi(): apigateway.RestApi {
    return new apigateway.RestApi(this, `${this.useCase}Api-${this.disambiguator}`, {
      restApiName: `NovaAct ${this.useCase} API-${this.disambiguator}`,
      description: `API for NovaAct ${this.useCase} functionality`,
      deployOptions: {
        stageName: this.stage,
      },
    });
  }

  /**
   * Create Lambda function with dedicated role and common environment variables
   * Each function gets its own IAM role for least privilege
   */
  protected createLambdaFunction(
    config: {
      id: string;
      functionName: string;
      handler: string;
      environment?: Record<string, string>;
    },
    props: BaseStepFunctionStackProps,
  ): IFunction {
    // Create dedicated role for this specific Lambda function
    const functionRole = new Role(this, `${config.id}Role-${this.disambiguator}`, {
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
      description: `Dedicated role for ${config.functionName}`,
    });

    // Add SES permissions if email notifications are enabled
    if (this.notificationChannels.includes(NotificationChannel.EMAIL)) {
      functionRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['ses:SendEmail', 'ses:SendRawEmail'],
          resources: [`arn:aws:ses:${this.region}:${this.account}:identity/*`],
        }),
      );
    }

    // Add Secrets Manager permissions if Slack is enabled
    if (this.slackSecretsName) {
      // Construct ARN manually to avoid cross-stack reference and cyclic dependency
      const secretArn = `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${this.slackSecretsName}-*`;
      functionRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ['secretsmanager:GetSecretValue'],
          resources: [secretArn],
        }),
      );
    }

    const baseEnvironment: Record<string, string> = {
      CONNECTIONS_TABLE: props.connectionsTable.tableName,
      EXECUTIONS_TABLE: props.executionsTable.tableName,
      DCV_LIBRARY_BASE_URL: 'https://dcm1zz7un8kem.cloudfront.net',
      SPA_BUCKET_NAME: this.spaBucket.bucketName,
      API_BASE_URL: `https://${this.api.restApiId}.execute-api.${this.region}.amazonaws.com/${this.stage}`,
      API_PATH_PREFIX: `/api/v1/${this.useCase.toLowerCase()}`,
      SUPPORTED_NOTIFICATION_CHANNELS: JSON.stringify(this.notificationChannels),
    };

    if (this.slackSecretsName) {
      baseEnvironment.SLACK_SECRETS = this.slackSecretsName;
    }

    return createLambdaFunction(
      this,
      {
        id: config.id,
        functionName: config.functionName,
        handler: config.handler,
        role: functionRole,
        environment: config.environment,
      },
      baseEnvironment,
    );
  }

  /** Abstract method to create the Step Function workflow - must be implemented by subclasses */
  protected abstract createStepFunctionFlow<T extends BaseStepFunctionStackProps>(props: T): StateMachine;

  /** Abstract method to set up API Gateway Lambda integrations - must be implemented by subclasses */
  protected abstract setupApiLambdas<T extends BaseStepFunctionStackProps>(props: T): void;

  /** Helper method to create and return the API authorizer */
  protected createApiAuthorizer(props: BaseStepFunctionStackProps): apigateway.RequestAuthorizer {
    // Create Lambda authorizer function to validate tokens
    const authorizerFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_AuthorizerFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-Authorizer-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.authorizer.authorizer_handler`,
      },
      props,
    );

    // Grant authorizer read access to executions table for token validation
    props.executionsTable.grantReadData(authorizerFunction);

    /**
     * Custom Lambda authorizer for token-based authentication
     *
     * The authorizer validates the eventId token from the Authorization header
     * against DynamoDB and returns an IAM policy allowing or denying access.
     *
     * Benefits over SigV4 presigned URLs:
     * - No credential expiration issues (sessions can last up to 24 hours)
     * - No need for periodic credential refresh
     * - Simpler client-side code (just add Authorization header)
     * - Server-side token validation on every request
     * - TTL still enforced via DynamoDB
     *
     * Authorization header format: "Bearer <eventId>"
     *
     * Important: We explicitly apply the authorizer to each POST method rather than using
     * defaultMethodOptions. This is because:
     * 1. Browser CORS preflight sends OPTIONS requests WITHOUT authentication headers
     * 2. If we used defaultMethodOptions, it would require authentication for preflight
     * 3. This would cause "403 Forbidden - CORS header missing" errors in the browser
     *
     * By explicitly setting auth only on POST methods, we ensure:
     * - OPTIONS preflight requests succeed without authentication
     * - Actual POST requests require valid tokens
     * - CORS works correctly with authenticated API Gateway endpoints
     */
    return new apigateway.RequestAuthorizer(this, `${this.useCase}ApiAuthorizer-${this.disambiguator}`, {
      handler: authorizerFunction,
      identitySources: [apigateway.IdentitySource.header('Authorization')],
      authorizerName: `${this.useCase}-Authorizer-${this.disambiguator}`,
      resultsCacheTtl: cdk.Duration.minutes(5), // Cache authorization results for 5 minutes
    });
  }

  /** Helper method to add CORS OPTIONS method to a resource */
  protected addCorsOptionsMethod(resource: apigateway.Resource): void {
    const corsIntegrationOptions: apigateway.IntegrationOptions = {
      integrationResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': "'*'",
            'method.response.header.Access-Control-Allow-Methods': "'GET,POST,PUT,DELETE,OPTIONS'",
            'method.response.header.Access-Control-Allow-Headers': CORS_HEADERS_STRING,
          },
        },
      ],
      passthroughBehavior: apigateway.PassthroughBehavior.NEVER,
      requestTemplates: {
        'application/json': '{"statusCode": 200}',
      },
    };

    const corsMethodResponses: apigateway.MethodResponse[] = [
      {
        statusCode: '200',
        responseParameters: {
          'method.response.header.Access-Control-Allow-Origin': true,
          'method.response.header.Access-Control-Allow-Methods': true,
          'method.response.header.Access-Control-Allow-Headers': true,
        },
      },
    ];

    resource.addMethod('OPTIONS', new apigateway.MockIntegration(corsIntegrationOptions), {
      authorizationType: apigateway.AuthorizationType.NONE,
      methodResponses: corsMethodResponses,
    });
  }

  /** Helper method to set up CORS error responses */
  protected setupCorsErrorResponses(): void {
    /** Add CORS headers to API Gateway error responses */
    this.api.addGatewayResponse('Default4XX', {
      type: apigateway.ResponseType.DEFAULT_4XX,
      responseHeaders: {
        'Access-Control-Allow-Origin': "'*'",
        'Access-Control-Allow-Headers': CORS_HEADERS_STRING,
      },
    });

    this.api.addGatewayResponse('Default5XX', {
      type: apigateway.ResponseType.DEFAULT_5XX,
      responseHeaders: {
        'Access-Control-Allow-Origin': "'*'",
        'Access-Control-Allow-Headers': CORS_HEADERS_STRING,
      },
    });
  }
}
