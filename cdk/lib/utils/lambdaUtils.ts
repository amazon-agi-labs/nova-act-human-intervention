/**
 * Utility functions for creating Lambda functions with consistent configuration.
 *
 * @remarks
 * This module provides helper functions to create Lambda functions with standardized
 * settings across the NovaAct infrastructure, including:
 * - Consistent runtime, memory, and timeout configuration
 * - Automatic log group creation with configurable retention
 * - Asset-based deployment from local lambda-packages directory
 * - Environment variable merging (base + function-specific)
 *
 * @packageDocumentation
 */
import { Construct } from 'constructs';
import { Function, IFunction } from 'aws-cdk-lib/aws-lambda';
import { Role } from 'aws-cdk-lib/aws-iam';
import { LogGroup, RetentionDays } from 'aws-cdk-lib/aws-logs';
import { Code } from 'aws-cdk-lib/aws-lambda';
import { CommonLambdaConfig } from '../models';

/**
 * Configuration interface for Lambda function creation.
 *
 * @remarks
 * All Lambda functions in the NovaAct infrastructure use this interface to ensure
 * consistent configuration patterns.
 */
export interface LambdaConfig {
  /** Unique CDK construct ID for this Lambda function */
  id: string;
  /** Physical AWS Lambda function name (must be unique within account/region) */
  functionName: string;
  /** Python handler in format 'module.path.function_name' */
  handler: string;
  /** Function-specific environment variables (merged with base environment) */
  environment?: Record<string, string>;
  /** IAM role for Lambda execution (if not provided, CDK creates default role) */
  role?: Role;
  /** CloudWatch Logs retention period (defaults to ONE_YEAR) */
  logRetentionDays?: RetentionDays;
  /** Human-readable description of Lambda function purpose */
  description?: string;
}

/**
 * Creates a Lambda function with standardized configuration and asset-based deployment.
 *
 * @remarks
 * This factory function ensures all Lambda functions in the NovaAct infrastructure
 * are created with consistent settings:
 *
 * **Configuration Applied:**
 * - Runtime: Python 3.12
 * - Memory: 256 MB
 * - Timeout: 10 minutes
 * - Architecture: x86_64
 * - Log retention: 1 year (configurable)
 *
 * **Environment Variables:**
 * Environment variables are merged in order of precedence:
 * 1. Base environment (stack-level settings like table names, API URLs)
 * 2. Function-specific environment (config.environment)
 *
 * **Log Groups:**
 * When a custom IAM role is provided, a dedicated log group is created with
 * configurable retention. Without a custom role, CDK creates a default log group.
 *
 * **Lambda Code Deployment:**
 * Uses Code.fromAsset() to deploy Lambda code from the lambda-packages/handlers
 * directory. This directory must be built using the build_lambda_package.py script
 * before running `cdk deploy`.
 *
 * @param scope - The CDK construct scope (parent stack or construct)
 * @param config - Lambda function configuration (name, handler, environment, etc.)
 * @param baseEnvironment - Base environment variables shared across multiple functions (e.g., table names)
 *
 * @returns AWS Lambda function interface that can be granted permissions or used in integrations
 *
 * @example
 * ```typescript
 * const connectHandler = createLambdaFunction(
 *   this,
 *   {
 *     id: 'ConnectHandler',
 *     functionName: 'HITL-ConnectHandler-alpha',
 *     handler: 'amzn_nova_act_human_intervention.handlers.websocket_connect',
 *     role: customRole,
 *   },
 *   {
 *     CONNECTIONS_TABLE: connectionsTable.tableName,
 *     EXECUTIONS_TABLE: executionsTable.tableName,
 *   }
 * );
 * ```
 */
export function createLambdaFunction(
  scope: Construct,
  config: LambdaConfig,
  baseEnvironment: Record<string, string> = {},
): IFunction {
  return new Function(scope, config.id, {
    functionName: config.functionName,
    description: config.description || `Updated at ${new Date().toISOString()}`,
    code: Code.fromAsset('lambda-packages/handlers'),
    handler: config.handler,
    role: config.role,
    logGroup: config.role
      ? new LogGroup(scope, `${config.id}LogGroup`, {
          retention: config.logRetentionDays || RetentionDays.ONE_YEAR,
        })
      : undefined,
    runtime: CommonLambdaConfig.RUNTIME,
    architecture: CommonLambdaConfig.ARCHITECTURE,
    timeout: CommonLambdaConfig.TIMEOUT_SECONDS,
    memorySize: CommonLambdaConfig.MEMORY_SIZE,
    environment: { ...baseEnvironment, ...config.environment },
  });
}
