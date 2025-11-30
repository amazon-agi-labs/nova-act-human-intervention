/**
 * Notification channels available for alerting users about human intervention requests.
 *
 * @remarks
 * - EMAIL: Sends notifications via AWS SES. Requires SES verified email addresses in your AWS account.
 * - SLACK: Sends notifications via Slack App SDK. Requires Slack bot token stored in AWS Secrets Manager.
 *          The secret should contain JSON: {"slackBotToken": "xoxb-..."}
 *
 * @example
 * ```typescript
 * const notificationChannels = [
 *   NotificationChannel.EMAIL,
 *   NotificationChannel.SLACK
 * ];
 * ```
 */
export enum NotificationChannel {
  /** Email notifications via AWS SES */
  EMAIL = 'Email',
  /** Slack notifications via Slack App SDK (bot token from Secrets Manager) */
  SLACK = 'Slack',
}

/**
 * Use cases supported by the human intervention system.
 *
 * @remarks
 * - APPROVAL: Used for human approval/rejection workflows (e.g., code review, content moderation)
 * - UI_TAKEOVER: Used for complex UI interactions (e.g., CAPTCHA solving, multi-factor authentication)
 *
 * Each use case has its own Step Function workflow and API endpoints.
 *
 * @example
 * ```typescript
 * const approvalStack = new ApprovalStepFunctionStack(app, 'Approval', {
 *   useCase: UseCase.APPROVAL,
 *   // ...
 * });
 * ```
 */
export enum UseCase {
  /** Browser takeover for complex UI interactions (CAPTCHA, forms, MFA) */
  UI_TAKEOVER = 'UITakeover',
  /** Human approval/rejection workflow with optional screenshot context */
  APPROVAL = 'Approval',
}
