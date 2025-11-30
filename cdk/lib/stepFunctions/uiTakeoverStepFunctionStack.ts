/**
 * Step Function workflow stack for UI Takeover human intervention.
 *
 * @remarks
 * This stack implements UI takeover workflows where automation hands off browser
 * control to a human to complete complex UI interactions.
 *
 * **Use Cases:**
 * - CAPTCHA solving
 * - Multi-factor authentication (MFA)
 * - Complex form filling with dynamic validation
 * - Interactive troubleshooting
 * - Human verification of visual elements
 *
 * **Workflow Flow:**
 * 1. Generate SPA with browser takeover instructions
 * 2. Transfer browser session to human via Bedrock Agent Core
 * 3. Poll every 30 seconds to check for task completion
 * 4. On completion, transfer control back to automation
 * 5. Emit EventBridge event with completion status
 *
 * **SPA Features:**
 * - Browser session handoff UI
 * - Real-time session status
 * - Task completion confirmation
 * - Session expiration countdown
 * - Instructions for human intervention
 *
 * **API Endpoints:**
 * - POST /api/v1/uitakeover/browser-session-info: Get browser session details
 * - POST /api/v1/uitakeover/complete-task: Mark task as completed
 * - POST /api/v1/uitakeover/task-status: Check workflow status
 * - POST /api/v1/uitakeover/terminate-workflow: Cancel workflow
 * - POST /api/v1/uitakeover/view-details: Get workflow details
 *
 * **Bedrock Integration:**
 * Integrates with Amazon Bedrock Agent Core for browser session management,
 * allowing seamless handoff between automation and human control.
 *
 * **Timeout:** 24 hours (configurable in state machine definition)
 *
 * @packageDocumentation
 */
import { Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  Choice,
  Condition,
  DefinitionBody,
  StateMachine,
  Succeed,
  TaskInput,
  Wait,
  WaitTime,
  Fail,
  Errors,
} from 'aws-cdk-lib/aws-stepfunctions';
import { EventBridgePutEvents, LambdaInvoke } from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Rule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { ServicePrincipal } from 'aws-cdk-lib/aws-iam';
import { BaseStepFunctionStack, BaseStepFunctionStackProps } from './baseStepFunctionStack';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import { LambdaIntegration } from 'aws-cdk-lib/aws-apigateway';

/**
 * Configuration properties for UI Takeover Step Function stack.
 *
 * @remarks
 * Extends base properties with CloudFront distribution for SPA delivery.
 */
interface UITakeoverStepFunctionStackProps extends BaseStepFunctionStackProps {
  /** CloudFront distribution for serving generated SPA content */
  readonly cloudFrontDistribution: cloudfront.IDistribution;
}

/**
 * Step Function stack implementing browser takeover workflows for complex UI interactions.
 *
 * @remarks
 * Creates a state machine that hands off browser control to humans for tasks
 * that automation cannot complete (CAPTCHA, MFA, etc.).
 *
 * **Resources Created:**
 * - Step Function state machine with 30-second polling
 * - Lambda functions for SPA generation, session management, and completion checking
 * - REST API endpoints for SPA interactions
 * - EventBridge rule for state machine completion handling
 * - IAM permissions for Bedrock Agent Core browser session APIs
 *
 * @example
 * ```typescript
 * const uiTakeoverStack = new UITakeoverStepFunctionStack(app, 'UITakeover', {
 *   env: { account: '123456789012', region: 'us-east-1' },
 *   stage: 'production',
 *   isProd: true,
 *   disambiguator: 'my-company',
 *   useCase: UseCase.UI_TAKEOVER,
 *   notificationChannels: [NotificationChannel.EMAIL],
 *   connectionsTable: storage.connectionsTable,
 *   executionsTable: storage.executionsTable,
 *   spaBucket: storage.spaBucket,
 *   cloudFrontDistribution: storage.cloudFrontDistribution,
 * });
 * ```
 */
export class UITakeoverStepFunctionStack extends BaseStepFunctionStack {
  /** Step Function state machine for UI takeover workflow */
  public readonly stateMachine: StateMachine;
  /** CloudFront distribution for SPA delivery */
  private readonly cloudFrontDistribution: cloudfront.IDistribution;

  constructor(scope: Construct, id: string, props: UITakeoverStepFunctionStackProps) {
    super(scope, id, props);

    // Use CloudFront distribution from StorageStack
    this.cloudFrontDistribution = props.cloudFrontDistribution;

    this.stateMachine = this.createStepFunctionFlow(props);
    this.setupEventBridgeRule(props);
  }

  /** Set up API Gateway Lambda integrations for UI Takeover */
  protected setupApiLambdas<T extends BaseStepFunctionStackProps>(props: T): void {
    // Cast to UITakeoverStepFunctionStackProps since we know this is a UI Takeover stack
    // TypeScript requires casting through 'unknown' first for type safety
    const uiTakeoverProps = props as unknown as UITakeoverStepFunctionStackProps;

    const getBrowserSessionInfoFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_GetBrowserSessionInfoFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-GetBrowserSessionInfo-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.browser_session_info_handler`,
      },
      uiTakeoverProps,
    );

    const completeTaskFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_CompleteTaskFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-CompleteTask-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.complete_task_handler`,
      },
      uiTakeoverProps,
    );

    const taskStatusFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_TaskStatusFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-TaskStatus-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.task_status_handler`,
      },
      uiTakeoverProps,
    );

    const terminateWorkflowFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_TerminateWorkflowFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-TerminateWorkflow-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.terminate_workflow_handler`,
      },
      uiTakeoverProps,
    );

    const viewDetailsFunction = this.createLambdaFunction(
      {
        id: `${this.useCase}SpaApi_ViewDetailsFunction-${this.disambiguator}`,
        functionName: `${this.useCase}-SpaApi-ViewDetails-${this.disambiguator}`,
        handler: `amzn_nova_act_human_intervention.workflows.ui_takeover.api.handlers.view_details_handler`,
      },
      uiTakeoverProps,
    );

    // Grant permissions
    uiTakeoverProps.executionsTable.grantReadWriteData(getBrowserSessionInfoFunction);
    uiTakeoverProps.executionsTable.grantReadWriteData(completeTaskFunction);
    uiTakeoverProps.executionsTable.grantReadData(taskStatusFunction);
    uiTakeoverProps.executionsTable.grantReadWriteData(terminateWorkflowFunction);
    uiTakeoverProps.executionsTable.grantReadData(viewDetailsFunction);

    uiTakeoverProps.connectionsTable.grantReadWriteData(getBrowserSessionInfoFunction);
    uiTakeoverProps.connectionsTable.grantReadWriteData(completeTaskFunction);
    uiTakeoverProps.connectionsTable.grantReadData(taskStatusFunction);
    uiTakeoverProps.connectionsTable.grantReadData(terminateWorkflowFunction);
    uiTakeoverProps.connectionsTable.grantReadData(viewDetailsFunction);

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

    // Grant bedrock-agentcore permissions to getBrowserSessionInfoFunction
    // Ref: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-onboarding.html
    getBrowserSessionInfoFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['bedrock-agentcore:GetBrowserSession', 'bedrock-agentcore:ConnectBrowserLiveViewStream'],
        resources: [
          `arn:aws:bedrock-agentcore:${this.region}:aws:browser/aws.browser.v1`,
          `arn:aws:bedrock-agentcore:${this.region}:${this.account}:browser/aws.browser.v1`,
        ],
      }),
    );

    // Create API resources
    const apiResource = this.api.root.addResource('api').addResource('v1');
    const useCaseResource = apiResource.addResource(this.useCase.toLowerCase());

    // Create authorizer
    const authorizer = this.createApiAuthorizer(uiTakeoverProps);

    const authMethodOptions: apigateway.MethodOptions = {
      authorizationType: apigateway.AuthorizationType.CUSTOM,
      authorizer: authorizer,
    };

    // Create endpoint resources
    const sessionInfoResource = useCaseResource.addResource('browser-session-info');
    const completeTaskResource = useCaseResource.addResource('complete-task');
    const taskStatusResource = useCaseResource.addResource('task-status');
    const terminateWorkflowResource = useCaseResource.addResource('terminate-workflow');
    const viewDetailsResource = useCaseResource.addResource('view-details');

    // Add POST methods with authorization
    sessionInfoResource.addMethod('POST', new LambdaIntegration(getBrowserSessionInfoFunction), authMethodOptions);
    completeTaskResource.addMethod('POST', new LambdaIntegration(completeTaskFunction), authMethodOptions);
    taskStatusResource.addMethod('POST', new LambdaIntegration(taskStatusFunction), authMethodOptions);
    terminateWorkflowResource.addMethod('POST', new LambdaIntegration(terminateWorkflowFunction), authMethodOptions);
    viewDetailsResource.addMethod('POST', new LambdaIntegration(viewDetailsFunction), authMethodOptions);

    // Add CORS OPTIONS methods
    this.addCorsOptionsMethod(useCaseResource);
    this.addCorsOptionsMethod(sessionInfoResource);
    this.addCorsOptionsMethod(completeTaskResource);
    this.addCorsOptionsMethod(taskStatusResource);
    this.addCorsOptionsMethod(terminateWorkflowResource);
    this.addCorsOptionsMethod(viewDetailsResource);

    // Setup CORS error responses
    this.setupCorsErrorResponses();
  }

  /** Create the UI takeover Step Function workflow */
  protected createStepFunctionFlow<T extends BaseStepFunctionStackProps>(props: T): StateMachine {
    const spaGeneratorAndSaver = this.createLambdaFunction(
      {
        id: `${this.useCase}StepFunction_SpaGenerator-${this.disambiguator}`,
        functionName: `${this.useCase}-StepFunction-SpaGenerator-${this.disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.spa_generator_handler',
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
        handler: 'amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.confirm_if_answered',
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

    /** Step Function task to check if user has completed the task */
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

    /** Choice state to determine if task is completed or needs to wait */
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
  private setupEventBridgeRule(props: UITakeoverStepFunctionStackProps) {
    const completionLambda = this.createLambdaFunction(
      {
        id: `${this.useCase}StepFunction_CompletionLambda-${this.disambiguator}`,
        functionName: `${this.useCase}-StepFunction-Completion-${this.disambiguator}`,
        handler: 'amzn_nova_act_human_intervention.workflows.ui_takeover.sfn.handlers.completion_handler',
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
