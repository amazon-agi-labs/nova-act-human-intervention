/**
 * Step Function workflow stack for Approval-based human intervention.
 *
 * @remarks
 * This stack implements approval workflows where a human reviews information
 * and makes an approve/reject decision.
 *
 * **Use Cases:**
 * - Code review approvals
 * - Content moderation
 * - Financial transaction verification
 * - Policy compliance checks
 * - Manual validation of automated actions
 *
 * **Workflow Flow:**
 * 1. Generate SPA with approval UI (includes screenshots if provided)
 * 2. Send notifications to configured channels (EMAIL/SLACK)
 * 3. Poll every 30 seconds to check for user response
 * 4. On completion, emit EventBridge event with decision
 * 5. Notify WebSocket connections of completion
 *
 * **SPA Features:**
 * - Approve/Reject buttons
 * - Optional comment field for justification
 * - Screenshot display (if provided during invocation)
 * - Session expiration countdown
 *
 * **API Endpoints:**
 * - POST /api/v1/approval/record-response: Submit approval decision
 * - POST /api/v1/approval/task-status: Check workflow status
 * - POST /api/v1/approval/terminate-workflow: Cancel workflow
 * - POST /api/v1/approval/view-details: Get workflow details
 *
 * **Screenshot Storage:**
 * Screenshots are stored in a dedicated S3 bucket with 24-hour lifecycle.
 * The SPA generator embeds screenshots in the approval interface for context.
 *
 * **Timeout:** 24 hours (configurable in state machine definition)
 *
 * @packageDocumentation
 */
import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  Choice,
  Condition,
  DefinitionBody,
  Errors,
  Fail,
  StateMachine,
  Succeed,
  TaskInput,
  Wait,
  WaitTime,
} from 'aws-cdk-lib/aws-stepfunctions';
import { EventBridgePutEvents, LambdaInvoke } from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Rule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import { ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { BaseStepFunctionStack, BaseStepFunctionStackProps } from './baseStepFunctionStack';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import { LambdaIntegration } from 'aws-cdk-lib/aws-apigateway';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';

/**
 * Configuration properties for Approval Step Function stack.
 *
 * @remarks
 * Extends base properties with CloudFront distribution for SPA delivery.
 */
interface ApprovalStepFunctionStackProps extends BaseStepFunctionStackProps {
  /** CloudFront distribution for serving generated SPA content */
  readonly cloudFrontDistribution: cloudfront.IDistribution;
}

/**
 * Step Function stack implementing approval-based human intervention workflows.
 *
 * @remarks
 * Creates a state machine that generates an approval SPA, waits for user decision,
 * and emits completion events.
 *
 * **Resources Created:**
 * - Step Function state machine with 30-second polling
 * - Screenshot S3 bucket with 24-hour lifecycle
 * - Lambda functions for SPA generation and completion checking
 * - REST API endpoints for SPA interactions
 * - EventBridge rule for state machine completion handling
 *
 * @example
 * ```typescript
 * const approvalStack = new ApprovalStepFunctionStack(app, 'Approval', {
 *   env: { account: '123456789012', region: 'us-east-1' },
 *   stage: 'production',
 *   isProd: true,
 *   disambiguator: 'my-company',
 *   useCase: UseCase.APPROVAL,
 *   notificationChannels: [NotificationChannel.EMAIL, NotificationChannel.SLACK],
 *   connectionsTable: storage.connectionsTable,
 *   executionsTable: storage.executionsTable,
 *   spaBucket: storage.spaBucket,
 *   cloudFrontDistribution: storage.cloudFrontDistribution,
 * });
 * ```
 */
export class ApprovalStepFunctionStack extends BaseStepFunctionStack {
  /** Step Function state machine for approval workflow */
  public readonly stateMachine: StateMachine;
  /** S3 bucket for temporary screenshot storage (24-hour lifecycle) */
  public readonly screenshotBucket: s3.Bucket;
  /** KMS key for screenshot bucket encryption */
  public readonly screenshotEncryptionKey: kms.Key;
  /** CloudFront distribution for SPA delivery */
  private readonly cloudFrontDistribution: cloudfront.IDistribution;

  constructor(scope: Construct, id: string, props: ApprovalStepFunctionStackProps) {
    super(scope, id, props);

    // Use CloudFront distribution from StorageStack
    this.cloudFrontDistribution = props.cloudFrontDistribution;

    // Disambiguator is set in parent class constructor
    const disambiguator = this.disambiguator;

    // Create customer-managed KMS key for screenshot encryption
    this.screenshotEncryptionKey = new kms.Key(this, `ScreenshotEncryptionKey-${disambiguator}`, {
      description: `Nova Act HITL Screenshot Encryption Key - ${disambiguator}`,
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Create S3 bucket for temporary screenshot storage (Approval-specific)
    this.screenshotBucket = new s3.Bucket(this, `ScreenshotBucket-${disambiguator}`, {
      bucketName: `nova-act-hitl-most-recent-screenshots-${this.account}-${disambiguator}`,
      versioned: false,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.screenshotEncryptionKey,
      bucketKeyEnabled: true, // Reduce KMS costs
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      lifecycleRules: [
        {
          id: 'DeleteAfter1Day',
          enabled: true,
          expiration: Duration.days(1),
        },
      ],
    });

    this.stateMachine = this.createStepFunctionFlow(props);
    this.setupEventBridgeRule(props);
  }

  /** Set up API Gateway Lambda integrations for Approval */
  protected setupApiLambdas<T extends BaseStepFunctionStackProps>(props: T): void {
    // Cast to ApprovalStepFunctionStackProps since we know this is an Approval stack
    // TypeScript requires casting through 'unknown' first due to additional properties
    const approvalProps = props as unknown as ApprovalStepFunctionStackProps;

    const recordResponseFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_RecordResponseFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-RecordResponse-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.approval.api.handlers.record_response_handler`,
      },
      approvalProps,
    );

    const taskStatusFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_TaskStatusFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-TaskStatus-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.approval.api.handlers.task_status_handler`,
      },
      approvalProps,
    );

    const terminateWorkflowFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_TerminateWorkflowFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-TerminateWorkflow-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.approval.api.handlers.terminate_workflow_handler`,
      },
      approvalProps,
    );

    const viewDetailsFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_ViewDetailsFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-ViewDetails-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.approval.api.handlers.view_details_handler`,
      },
      approvalProps,
    );

    // Grant permissions
    approvalProps.executionsTable.grantReadWriteData(recordResponseFunction);
    approvalProps.executionsTable.grantReadData(taskStatusFunction);
    approvalProps.executionsTable.grantReadWriteData(terminateWorkflowFunction);
    approvalProps.executionsTable.grantReadData(viewDetailsFunction);

    approvalProps.connectionsTable.grantReadData(recordResponseFunction);
    approvalProps.connectionsTable.grantReadData(taskStatusFunction);
    approvalProps.connectionsTable.grantReadData(terminateWorkflowFunction);
    approvalProps.connectionsTable.grantReadData(viewDetailsFunction);

    // Grant Step Functions stop execution permission to terminateWorkflowFunction
    // Scoped to specific state machine executions for security
    terminateWorkflowFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['states:StopExecution'],
        resources: [
          `arn:aws:states:${this.region}:${this.account}:execution:NovaAct${this.useCase}Workflow-${this.disambiguator}:*`,
        ],
      }),
    );

    // Create API resources
    const apiResource = this.api.root.addResource('api').addResource('v1');
    const useCaseResource = apiResource.addResource(this.useCase.toLowerCase());

    // Create authorizer
    const authorizer = this.createApiAuthorizer(approvalProps);

    const authMethodOptions: apigateway.MethodOptions = {
      authorizationType: apigateway.AuthorizationType.CUSTOM,
      authorizer: authorizer,
    };

    // Create endpoint resources
    const recordResponseResource = useCaseResource.addResource('record-response');
    const taskStatusResource = useCaseResource.addResource('task-status');
    const terminateWorkflowResource = useCaseResource.addResource('terminate-workflow');
    const viewDetailsResource = useCaseResource.addResource('view-details');

    // Add POST methods with authorization
    recordResponseResource.addMethod('POST', new LambdaIntegration(recordResponseFunction), authMethodOptions);
    taskStatusResource.addMethod('POST', new LambdaIntegration(taskStatusFunction), authMethodOptions);
    terminateWorkflowResource.addMethod('POST', new LambdaIntegration(terminateWorkflowFunction), authMethodOptions);
    viewDetailsResource.addMethod('POST', new LambdaIntegration(viewDetailsFunction), authMethodOptions);

    // Add CORS OPTIONS methods
    this.addCorsOptionsMethod(useCaseResource);
    this.addCorsOptionsMethod(recordResponseResource);
    this.addCorsOptionsMethod(taskStatusResource);
    this.addCorsOptionsMethod(terminateWorkflowResource);
    this.addCorsOptionsMethod(viewDetailsResource);

    // Setup CORS error responses
    this.setupCorsErrorResponses();
  }

  /** Create the approval Step Function workflow */
  protected createStepFunctionFlow<T extends BaseStepFunctionStackProps>(props: T): StateMachine {
    // Cast to ApprovalStepFunctionStackProps to access CloudFront properties
    const spaGeneratorAndSaver = this.createLambdaFunction(
      {
        id: `${this.useCase}StepFunction_SpaGenerator-${this.disambiguator}`,
        functionName: `${this.useCase}-StepFunction-SpaGenerator-${this.disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.workflows.approval.sfn.handlers.spa_generator_handler',
        environment: {
          SPA_CLOUDFRONT_DOMAIN: this.cloudFrontDistribution.distributionDomainName,
        },
      },
      props,
    );

    const confirmIfAnswered = this.createLambdaFunction(
      {
        id: `${this.useCase}StepFunction_ConfirmIfAnswered-${this.disambiguator}`,
        functionName: `${this.useCase}-StepFunction-ConfirmIfAnswered-${this.disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.workflows.approval.sfn.handlers.confirm_if_answered',
      },
      props,
    );

    props.executionsTable.grantReadWriteData(spaGeneratorAndSaver);
    props.executionsTable.grantReadWriteData(confirmIfAnswered);
    props.connectionsTable.grantReadWriteData(spaGeneratorAndSaver);
    props.connectionsTable.grantReadWriteData(confirmIfAnswered);

    // Grant SPA bucket permissions via IAM policy (not bucket policy) to avoid circular dependency
    // Since spaBucket comes from Storage stack, using grantReadWrite would create a circular reference
    spaGeneratorAndSaver.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['s3:GetObject', 's3:PutObject', 's3:PutObjectTagging', 's3:DeleteObject'],
        resources: [`${this.spaBucket.bucketArn}/*`],
      }),
    );

    // Grant screenshot bucket permissions for Approval workflow
    // screenshotBucket is in this stack, so grantRead/grantDelete is safe
    this.screenshotBucket.grantRead(spaGeneratorAndSaver);
    this.screenshotBucket.grantDelete(spaGeneratorAndSaver);

    // Grant KMS permissions for screenshot encryption/decryption
    this.screenshotEncryptionKey.grantEncryptDecrypt(spaGeneratorAndSaver);

    // Grant API Gateway Management API permissions for WebSocket messaging
    // Scoped to region/account - can't be more specific due to circular dependency with WebSocket stack
    spaGeneratorAndSaver.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['execute-api:ManageConnections', 'execute-api:Invoke'],
        resources: [`arn:aws:execute-api:${this.region}:${this.account}:*`],
      }),
    );

    /** Error Sink state to collect all handled errors */
    const errorSink = new Fail(this, `${this.useCase}ErrorSink-${this.disambiguator}`, {
      stateName: 'ErrorSink',
      errorPath: '$.error.Error',
      causePath: '$.error.Cause',
    });

    /** Step Function task to generate SPA interface */
    const generateSpaTask = new LambdaInvoke(this, `${this.useCase}GenerateSpaTask-${this.disambiguator}`, {
      lambdaFunction: spaGeneratorAndSaver,
      resultPath: '$.spaResult',
    }).addCatch(errorSink, {
      errors: [Errors.ALL],
      resultPath: '$.error',
    });

    /** Step Function task to check if user has completed the approval */
    const confirmTask = new LambdaInvoke(this, `${this.useCase}ConfirmIfAnsweredTask-${this.disambiguator}`, {
      lambdaFunction: confirmIfAnswered,
      resultPath: '$.confirmResult',
    }).addCatch(errorSink, {
      errors: [Errors.ALL],
      resultPath: '$.error',
    });

    /** Wait state before checking completion again */
    const waitTask = new Wait(this, `${this.useCase}WaitBeforeRetry-${this.disambiguator}`, {
      time: WaitTime.duration(Duration.seconds(30)),
    });

    /** Send completion notification via EventBridge */
    const completeTask = new EventBridgePutEvents(
      this,
      `${this.useCase}SendCompletionNotification-${this.disambiguator}`,
      {
        entries: [
          {
            source: `nova-act-${this.useCase.toLowerCase()}.workflow`,
            detailType: `${this.useCase} Completed`,
            detail: TaskInput.fromJsonPathAt('$.spaResult.Payload'),
          },
        ],
        resultPath: '$.completionResult',
      },
    ).addCatch(errorSink, {
      errors: [Errors.ALL],
      resultPath: '$.error',
    });

    const successState = new Succeed(this, `${this.useCase}WorkflowCompleted-${this.disambiguator}`);

    /** Choice state to determine if approval is completed or needs to wait */
    const checkAnswered = new Choice(this, `${this.useCase}CheckIfAnswered-${this.disambiguator}`)
      .when(Condition.booleanEquals('$.confirmResult.Payload', true), completeTask.next(successState))
      .otherwise(waitTask.next(confirmTask));

    const workflow = generateSpaTask.next(confirmTask).next(checkAnswered);

    return new StateMachine(this, `${this.useCase}Workflow-${this.disambiguator}`, {
      definitionBody: DefinitionBody.fromChainable(workflow),
      timeout: Duration.hours(24),
      stateMachineName: `NovaAct${this.useCase}Workflow-${this.disambiguator}`,
    });
  }

  /** Set up EventBridge rule to handle Step Function completion events */
  private setupEventBridgeRule(props: ApprovalStepFunctionStackProps) {
    const completionLambda = this.createLambdaFunction(
      {
        id: `${this.useCase}StepFunction_CompletionLambda-${this.disambiguator}`,
        functionName: `${this.useCase}-StepFunction-Completion-${this.disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.workflows.approval.sfn.handlers.completion_handler',
      },
      props,
    );

    const rule = new Rule(this, `${this.useCase}StepFunctionCompletionRule-${this.disambiguator}`, {
      eventPattern: {
        source: ['aws.states'],
        detailType: ['Step Functions Execution Status Change'],
        detail: {
          status: ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED'],
          stateMachineArn: [this.stateMachine.stateMachineArn],
        },
      },
    });

    rule.addTarget(new LambdaFunction(completionLambda));

    completionLambda.addPermission(`${this.useCase}AllowEventBridge`, {
      principal: new ServicePrincipal('events.amazonaws.com'),
      action: 'lambda:InvokeFunction',
      sourceArn: rule.ruleArn,
    });
    completionLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['execute-api:ManageConnections', 'execute-api:Invoke'],
        resources: [`arn:aws:execute-api:${this.region}:${this.account}:*`],
      }),
    );

    // Grant DynamoDB permissions to completionLambda
    props.executionsTable.grantReadWriteData(completionLambda);
    props.connectionsTable.grantReadWriteData(completionLambda);
  }
}
