#!/usr/bin/env node

import { App } from 'aws-cdk-lib';
import {
  StorageStack,
  WebsocketExecutorStack,
  ApprovalStepFunctionStack,
  UITakeoverStepFunctionStack,
  NotificationChannel,
  UseCase,
} from '../lib';

const app = new App();

const env = {
  account: process.env.DEPLOYMENT_ACCOUNT,
  region: process.env.DEPLOYMENT_REGION || 'us-east-1',
};

const stage = process.env.DEPLOYMENT_STAGE || 'dev';
const disambiguator = process.env.STACK_DISAMBIGUATOR || stage;
const isProd = stage === 'prod';

// Configure notification channels for all workflows
const notificationChannels = [NotificationChannel.EMAIL, NotificationChannel.SLACK];

const storageStack = new StorageStack(app, `NovaActHITL-Storage-${disambiguator}`, {
  env,
  stage,
  isProd,
  disambiguator,
  notificationChannels,
});

const approvalStack = new ApprovalStepFunctionStack(app, `NovaActHITL-Approval-${disambiguator}`, {
  env,
  stage,
  isProd,
  disambiguator,
  useCase: UseCase.APPROVAL,
  notificationChannels,
  connectionsTable: storageStack.connectionsTable,
  executionsTable: storageStack.executionsTable,
  spaBucket: storageStack.spaBucket,
  cloudFrontDistribution: storageStack.cloudFrontDistribution,
  slackSecretsName: storageStack.slackSecrets?.secretName,
});
approvalStack.addDependency(storageStack);

const uiTakeoverStack = new UITakeoverStepFunctionStack(app, `NovaActHITL-UITakeover-${disambiguator}`, {
  env,
  stage,
  isProd,
  disambiguator,
  useCase: UseCase.UI_TAKEOVER,
  notificationChannels,
  connectionsTable: storageStack.connectionsTable,
  executionsTable: storageStack.executionsTable,
  spaBucket: storageStack.spaBucket,
  cloudFrontDistribution: storageStack.cloudFrontDistribution,
  slackSecretsName: storageStack.slackSecrets?.secretName,
});
uiTakeoverStack.addDependency(storageStack);

const websocketStack = new WebsocketExecutorStack(app, `NovaActHITL-WebSocket-${disambiguator}`, {
  env,
  stage,
  isProd,
  disambiguator,
  allowedAccounts: [env.account!],
  notificationChannels,
  connectionsTable: storageStack.connectionsTable,
  executionsTable: storageStack.executionsTable,
  spaBucket: storageStack.spaBucket,
  slackSecretsName: storageStack.slackSecrets?.secretName,
  stateMachineArns: {
    [UseCase.APPROVAL]: approvalStack.stateMachine.stateMachineArn,
    [UseCase.UI_TAKEOVER]: uiTakeoverStack.stateMachine.stateMachineArn,
  },
  screenshotBucket: approvalStack.screenshotBucket,
});
websocketStack.addDependency(storageStack);
websocketStack.addDependency(approvalStack);
websocketStack.addDependency(uiTakeoverStack);

/**
 * Grant execution role access to screenshot KMS key for client uploads.
 *
 * @remarks
 * The execution role (created in WebSocketExecutorStack) needs KMS permissions
 * to encrypt screenshots when clients upload them to the screenshot bucket.
 * This grant is added here (after stack creation) to avoid circular dependencies.
 */
approvalStack.screenshotEncryptionKey.grantEncryptDecrypt(websocketStack.executionRole);

app.synth();
