/**
 * Constants for NovaAct Human Intervention
 */
import { Architecture, Runtime } from 'aws-cdk-lib/aws-lambda';
import { Duration } from 'aws-cdk-lib';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';

/**
 * Default configuration for all Lambda functions in the NovaAct infrastructure.
 */
export const CommonLambdaConfig = {
  /** Python runtime version */
  RUNTIME: Runtime.PYTHON_3_12,
  /** Memory allocation in MB */
  MEMORY_SIZE: 256,
  /** Maximum execution time */
  TIMEOUT_SECONDS: Duration.minutes(10),
  /** CPU architecture */
  ARCHITECTURE: Architecture.X86_64,
  /** CloudWatch Logs retention period */
  LOG_RETENTION_DAYS: RetentionDays.ONE_YEAR,
} as const;

/**
 * CORS headers for API Gateway responses
 * Includes all headers needed for browser-based SPA authentication
 */
export const CORS_HEADERS_STRING =
  "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent'";
