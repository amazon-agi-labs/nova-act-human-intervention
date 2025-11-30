/**
 * WebSocket API stack for real-time human intervention workflow execution.
 *
 * @remarks
 * This stack provides the WebSocket infrastructure for bidirectional real-time
 * communication between clients and the NovaAct workflow system.
 *
 * **Architecture:**
 * All WebSocket infrastructure is consolidated in this single stack to avoid
 * circular dependencies between API Gateway and Step Functions.
 *
 * **WebSocket Routes:**
 * - $connect: Establishes connection, stores in DynamoDB, validates IAM auth
 * - $disconnect: Cleanup connection record from DynamoDB
 * - $default: Fallback handler for unrecognized routes
 * - start-hitl-flow: Initiates human intervention workflow (Approval or UI Takeover)
 * - connection-refresh: Refreshes connection during long-running workflows
 *
 * **Lambda Handlers:**
 * - Connect: Validates IAM auth, stores connection in DynamoDB with TTL
 * - Disconnect: Removes connection record from DynamoDB
 * - HITL Flow: Starts Step Function execution for specified use case
 * - Connection Refresh: Extends connection TTL during active workflows
 * - SPA Cleanup: DynamoDB Stream consumer to delete expired SPA objects from S3
 *
 * **Authentication:**
 * Uses AWS SigV4 (IAM) authorization for WebSocket connections. Clients must
 * sign connection requests with valid AWS credentials.
 *
 * **Cross-Account Access:**
 * Supports multi-account deployments via execution role that can be assumed
 * from configured AWS accounts (Lambda, ECS Tasks, etc.).
 *
 * **DynamoDB Streams:**
 * Consumes executions table stream to automatically cleanup S3 SPA objects
 * when TTL expires DynamoDB records. This is necessary because:
 * - S3 lifecycle rules have minimum 24-hour expiration
 * - CloudFront URLs don't expire like S3 presigned URLs
 * - Immediate cleanup prevents access after session expiry
 *
 * **Connection Management:**
 * - Connections tracked in DynamoDB with TTL
 * - Automatic cleanup via TTL expiration
 * - Connection refresh extends TTL for long workflows
 * - WebSocket API Management permissions for message sending
 *
 * @packageDocumentation
 */
import { Construct } from 'constructs';
import { CfnOutput } from 'aws-cdk-lib';
import { Stack, StackProps } from 'aws-cdk-lib';
import { WebSocketApi, WebSocketStage, CfnStage } from 'aws-cdk-lib/aws-apigatewayv2';
import { WebSocketIamAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { WebSocketLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { CfnFunction } from 'aws-cdk-lib/aws-lambda';
import { Table } from 'aws-cdk-lib/aws-dynamodb';
import { DynamoEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { StartingPosition, FilterCriteria, FilterRule } from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import {
  Role,
  ServicePrincipal,
  PolicyStatement,
  PolicyDocument,
  Effect,
  CompositePrincipal,
  AccountPrincipal,
} from 'aws-cdk-lib/aws-iam';
import { UseCase, NotificationChannel } from '../models';
import { createLambdaFunction } from '../utils/lambdaUtils';

/**
 * Configuration properties for WebSocket executor stack.
 *
 * @remarks
 * Configures WebSocket API, Lambda handlers, and cross-account access.
 */
interface WebsocketExecutorStackProps extends StackProps {
  /** AWS deployment environment (account and region) */
  
  /** Deployment stage name (alpha, beta, gamma, prod) */
  readonly stage: string;
  /** Production flag affecting monitoring */
  readonly isProd: boolean;
  /** Disambiguator for multi-deployment scenarios */
  readonly disambiguator?: string;
  /** AWS account IDs allowed to assume execution role for cross-account workflows */
  readonly allowedAccounts?: string[];
  /** Notification channels for workflow alerts */
  readonly notificationChannels: NotificationChannel[];
  /** DynamoDB table for connection tracking */
  readonly connectionsTable: Table;
  /** DynamoDB table for execution state (with Streams for SPA cleanup) */
  readonly executionsTable: Table;
  /** S3 bucket for SPA asset storage */
  readonly spaBucket: s3.Bucket;
  /** State machine ARNs for each use case (APPROVAL, UI_TAKEOVER) */
  readonly stateMachineArns: Record<UseCase, string>;
  /** Optional screenshot bucket for Approval use case */
  readonly screenshotBucket?: s3.Bucket;
  /** Shared Secrets Manager secret name for Slack bot token (if SLACK channel configured) */
  readonly slackSecretsName?: string;
}

/**
 * WebSocket API stack providing real-time workflow execution infrastructure.
 *
 * @remarks
 * This stack creates a complete WebSocket API with all necessary Lambda handlers
 * and IAM roles for secure, cross-account human intervention workflows.
 *
 * **Resources Created:**
 * - WebSocket API with IAM authorization
 * - 5 Lambda handlers (connect, disconnect, HITL flow, refresh, cleanup)
 * - DynamoDB Stream consumer for SPA cleanup
 * - Execution role for cross-account access
 * - API Management permissions for all handlers
 *
 * **Why Single Stack:**
 * All WebSocket resources are in one stack to prevent circular dependencies
 * between API Gateway (needs Lambda ARNs) and Lambda (needs API endpoint).
 *
 * @example
 * ```typescript
 * const websocketStack = new WebsocketExecutorStack(app, 'WebSocket', {
 *   env: { account: '123456789012', region: 'us-east-1' },
 *   stage: 'production',
 *   isProd: true,
 *   disambiguator: 'my-company',
 *   allowedAccounts: ['987654321098'], // Cross-account access
 *   notificationChannels: [NotificationChannel.EMAIL],
 *   connectionsTable: storage.connectionsTable,
 *   executionsTable: storage.executionsTable,
 *   spaBucket: storage.spaBucket,
 *   stateMachineArns: {
 *     [UseCase.APPROVAL]: approvalStack.stateMachine.stateMachineArn,
 *     [UseCase.UI_TAKEOVER]: uiTakeoverStack.stateMachine.stateMachineArn,
 *   },
 *   screenshotBucket: approvalStack.screenshotBucket,
 * });
 * ```
 */
export class WebsocketExecutorStack extends Stack {
  /** WebSocket API Gateway instance */
  public readonly webSocketApi: WebSocketApi;
  /** WebSocket API deployment stage */
  public readonly webSocketStage: WebSocketStage;
  /** WebSocket connection URL (wss://<api-id>.execute-api.<region>.amazonaws.com/<stage>) */
  public readonly webSocketEndpoint: string;
  /** IAM role for cross-account workflow execution */
  public readonly executionRole: Role;
  /** Managed policy for assuming NovaAct HITL execution roles */
  public readonly assumeExecutionRolePolicy: iam.ManagedPolicy;

  constructor(scope: Construct, id: string, props: WebsocketExecutorStackProps) {
    super(scope, id, props);

    const disambiguator = props.disambiguator;

    const baseEnvironment: Record<string, string> = {
      CONNECTIONS_TABLE: props.connectionsTable.tableName,
      EXECUTIONS_TABLE: props.executionsTable.tableName,
      SPA_BUCKET_NAME: props.spaBucket.bucketName,
      EXECUTOR_ENDPOINT: '', // Will be updated after API creation
      STATE_MACHINE_ARNS: JSON.stringify(props.stateMachineArns),
      SUPPORTED_NOTIFICATION_CHANNELS: JSON.stringify(props.notificationChannels),
    };

    // Add Secrets Manager secret name if Slack is enabled
    if (props.slackSecretsName) {
      baseEnvironment.SLACK_SECRETS = props.slackSecretsName;
    }

    /** Lambda function for handling WebSocket connections */
    const connectHandler = createLambdaFunction(
      this,
      {
        id: `ConnectHandler-${disambiguator}`,
        functionName: `HITL-Invocation-ConnectHandler-${disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.executors.websocket.handlers.websocket_connect',
      },
      baseEnvironment,
    );

    /** Lambda function for handling WebSocket disconnections */
    const disconnectHandler = createLambdaFunction(
      this,
      {
        id: `DisconnectHandler-${disambiguator}`,
        functionName: `HITL-Invocation-DisconnectHandler-${disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.executors.websocket.handlers.websocket_disconnect',
      },
      baseEnvironment,
    );

    /** Lambda function for starting human-in-the-loop workflows */
    const hitlFlowHandler = createLambdaFunction(
      this,
      {
        id: `HitlFlowHandler-${disambiguator}`,
        functionName: `HITL-Invocation-HitlFlowHandler-${disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.executors.websocket.handlers.start_hitl_flow',
      },
      baseEnvironment,
    );

    /** Lambda function for handling connection refresh during URL expiry */
    const connectionRefreshHandler = createLambdaFunction(
      this,
      {
        id: `ConnectionRefreshHandler-${disambiguator}`,
        functionName: `HITL-Invocation-ConnectionRefreshHandler-${disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.executors.websocket.handlers.connection_refresh',
      },
      baseEnvironment,
    );

    /**
     * Lambda function for DynamoDB stream consumer to cleanup expired SPA objects
     *
     * This function processes DynamoDB Stream events from the executions table.
     * When DynamoDB TTL deletes an expired execution record, this handler deletes
     * the corresponding S3 object using the eventId.
     *
     * This is necessary because:
     * 1. S3 lifecycle rules have a minimum 24-hour expiration period
     * 2. CloudFront URLs have no expiration (unlike S3 presigned URLs)
     * 3. SPA objects must be deleted promptly to prevent access after session expiry
     *
     * Note: This handler is use case agnostic and located in the streams module
     * rather than websocket-specific handlers.
     */
    const spaCleanupHandler = createLambdaFunction(
      this,
      {
        id: `SpaCleanupHandler-${disambiguator}`,
        functionName: `HITL-Invocation-SpaCleanupHandler-${disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.executors.streams.handlers.cleanup_expired_spa_objects',
      },
      baseEnvironment,
    );

    /** Grant Secrets Manager permissions to cleanup handler if Slack is configured */
    if (props.slackSecretsName) {
      const slackSecretsArn = `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${props.slackSecretsName}-*`;
      spaCleanupHandler.addToRolePolicy(
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['secretsmanager:GetSecretValue'],
          resources: [slackSecretsArn],
        }),
      );
    }

    /** Grant DynamoDB and S3 permissions to all Lambda functions */
    [connectHandler, disconnectHandler, hitlFlowHandler, connectionRefreshHandler, spaCleanupHandler].forEach((fn) => {
      props.connectionsTable.grantReadWriteData(fn);
      props.executionsTable.grantReadWriteData(fn);
      props.spaBucket.grantReadWrite(fn);
    });

    /** Grant Step Functions execution permissions to HITL flow handler */
    hitlFlowHandler.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['states:StartExecution', 'states:DescribeExecution', 'states:StopExecution'],
        resources: Object.values(props.stateMachineArns).filter((arn) => arn !== ''),
      }),
    );

    /**
     * Configure DynamoDB Stream event source for SPA cleanup handler
     *
     * When DynamoDB TTL deletes expired records from the executions table,
     * the stream triggers this Lambda to delete corresponding SPA objects from S3.
     *
     * Configuration:
     * - TRIM_HORIZON: Process all existing stream records (for missed deletions during deployment)
     * - Batch size 10: Process up to 10 deletion events at once for efficiency
     * - Event filtering: Only invoke Lambda for REMOVE events (not INSERT/MODIFY)
     * - Enabled: Start processing immediately upon deployment
     */
    spaCleanupHandler.addEventSource(
      new DynamoEventSource(props.executionsTable, {
        startingPosition: StartingPosition.TRIM_HORIZON,
        batchSize: 10,
        enabled: true,
        filters: [
          FilterCriteria.filter({
            // This ensures that we only process
            // notifications for deletes.
            eventName: FilterRule.isEqual('REMOVE'),
          }),
        ],
      }),
    );

    /** WebSocket API with IAM authorization and Lambda integrations */
    this.webSocketApi = new WebSocketApi(this, `WebSocketApi-${disambiguator}`, {
      apiName: `NovaAct HITL Invoker API-${disambiguator}`,
      description: 'WebSocket API for real-time human intervention workflows',
      connectRouteOptions: {
        integration: new WebSocketLambdaIntegration(`ConnectIntegration-${disambiguator}`, connectHandler),
        authorizer: new WebSocketIamAuthorizer(),
      },
      disconnectRouteOptions: {
        integration: new WebSocketLambdaIntegration(`DisconnectIntegration-${disambiguator}`, disconnectHandler),
      },
      defaultRouteOptions: {
        integration: new WebSocketLambdaIntegration(`DefaultIntegration-${disambiguator}`, hitlFlowHandler),
      },
    });

    /** Custom route for starting HITL workflows */
    this.webSocketApi.addRoute('start-hitl-flow', {
      integration: new WebSocketLambdaIntegration(`StartHitlFlowIntegration-${disambiguator}`, hitlFlowHandler),
      returnResponse: true,
    });

    /** Custom route for refreshing connection during URL expiry */
    this.webSocketApi.addRoute('connection-refresh', {
      integration: new WebSocketLambdaIntegration(
        `ConnectionRefreshIntegration-${disambiguator}`,
        connectionRefreshHandler,
      ),
      returnResponse: true,
    });

    /** WebSocket deployment stage */
    this.webSocketStage = new WebSocketStage(this, `WebSocketStage-${disambiguator}`, {
      webSocketApi: this.webSocketApi,
      stageName: props.stage,
      autoDeploy: true,
    });

    /** Setting up logging for the API gateway */
    const cfnStage = this.webSocketStage.node.defaultChild as CfnStage;
    cfnStage.defaultRouteSettings = {
      dataTraceEnabled: false,
      detailedMetricsEnabled: true,
      loggingLevel: 'INFO',
    };

    /** Construct WebSocket endpoint URL */
    this.webSocketEndpoint = `wss://${this.webSocketApi.apiId}.execute-api.${this.region}.amazonaws.com/${this.webSocketStage.stageName}`;

    /** Update Lambda environment variables with WebSocket endpoint */
    [connectHandler, disconnectHandler, hitlFlowHandler, connectionRefreshHandler].forEach((fn) => {
      const cfnFunction = fn.node.defaultChild as CfnFunction;
      cfnFunction.addPropertyOverride('Environment.Variables.EXECUTOR_ENDPOINT', this.webSocketEndpoint);
    });

    /** Grant WebSocket API Management permissions to all handlers for sending messages to connections */
    // Now scoped to the specific WebSocket API that was just created
    [connectHandler, disconnectHandler, hitlFlowHandler, connectionRefreshHandler].forEach((fn) => {
      fn.addToRolePolicy(
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['execute-api:ManageConnections', 'execute-api:Invoke'],
          resources: [`arn:aws:execute-api:${this.region}:${this.account}:${this.webSocketApi.apiId}/*`],
        }),
      );
    });

    /** Configure cross-account access principals */
    const allowedAccounts = props.allowedAccounts || [this.account];
    const principals = [
      new ServicePrincipal('lambda.amazonaws.com'),
      new ServicePrincipal('ecs-tasks.amazonaws.com'),
      ...allowedAccounts.map((accountId) => new AccountPrincipal(accountId)),
    ];

    /** IAM role for client WebSocket API access and screenshot upload */
    const policyStatements = [
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['execute-api:ManageConnections', 'execute-api:Invoke'],
        resources: [`arn:aws:execute-api:${this.region}:${this.account}:${this.webSocketApi.apiId}/*`],
      }),
    ];

    // Add screenshot bucket permissions if provided (for Approval use case)
    if (props.screenshotBucket) {
      policyStatements.push(
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['s3:PutObject'],
          resources: [`${props.screenshotBucket.bucketArn}/*`],
        }),
      );
    }

    this.executionRole = new Role(this, `WebSocketExecutionRole-${disambiguator}`, {
      roleName: `NovaAct-HITL-ExecutionRole-${disambiguator}`,
      assumedBy: new CompositePrincipal(...principals),
      inlinePolicies: {
        WebSocketPolicy: new PolicyDocument({
          statements: policyStatements,
        }),
      },
    });

    /**
     * Managed policy for assuming NovaAct HITL execution roles
     *
     * This policy can be attached to any IAM role (user roles, Lambda execution roles, etc.)
     * to grant permission to assume execution roles matching the pattern NovaAct-HITL-ExecutionRole*
     */
    this.assumeExecutionRolePolicy = new iam.ManagedPolicy(this, `AssumeExecutionRolePolicy-${disambiguator}`, {
      managedPolicyName: `NovaAct-HITL-AssumeExecutionRole-${disambiguator}`,
      description: 'Allows assuming NovaAct HITL execution roles for human intervention workflows',
      statements: [
        new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ['sts:AssumeRole'],
          resources: [`arn:aws:iam::${this.account}:role/NovaAct-HITL-ExecutionRole*`],
        }),
      ],
    });

    /** CloudFormation stack outputs for easy reference */
    new CfnOutput(this, `NovaActHITL-WebSocket-${disambiguator}-Endpoint`, {
      value: this.webSocketEndpoint,
      description: 'WebSocket API Gateway endpoint URL for connecting to the HITL workflow system',
      exportName: `NovaActHITL-WebSocket-${disambiguator}-Endpoint`,
    });

    new CfnOutput(this, `NovaActHITL-WebSocket-${disambiguator}-ExecutionRoleArn`, {
      value: this.executionRole.roleArn,
      description: 'IAM execution role ARN for clients to assume when connecting to WebSocket API',
      exportName: `NovaActHITL-WebSocket-${disambiguator}-ExecutionRoleArn`,
    });

    new CfnOutput(this, `NovaActHITL-WebSocket-${disambiguator}-AssumeExecutionRolePolicyArn`, {
      value: this.assumeExecutionRolePolicy.managedPolicyArn,
      description: 'Managed policy ARN for assuming NovaAct HITL execution roles',
      exportName: `NovaActHITL-WebSocket-${disambiguator}-AssumeExecutionRolePolicyArn`,
    });
  }
}
