import logging
import os
import sys


class LoggingConfig:
    """Centralized logging configuration for the package.

    Provides consistent logging setup across AWS Lambda and local environments.
    Automatically detects Lambda environment and configures appropriately.
    """

    _configured = False

    @classmethod
    def _is_lambda_environment(cls) -> bool:
        """Check if running in AWS Lambda environment.

        Returns
        -------
        bool
            True if running in Lambda, False otherwise
        """
        return "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    @classmethod
    def setup_logging(
        cls,
        level: int = logging.INFO,
        format_string: str | None = None,
        logger_name: str = "amzn_nova_act_human_intervention_common",
    ) -> logging.Logger:
        """Setup logging configuration for the package.

        Parameters
        ----------
        level : int, default=logging.INFO
            Logging level
        format_string : str, optional
            Custom format string. If not provided, uses standard format
            with timestamp, name, level, and message.
        logger_name : str, default="amzn_nova_act_human_intervention_common"
            Logger name

        Returns
        -------
        logging.Logger
            Configured logger instance

        Notes
        -----
        In Lambda environments, only the log level is set as Lambda provides
        its own logging configuration. In other environments, logging is
        configured from scratch with the specified format.

        Examples
        --------
        Basic setup with default INFO level::

            >>> from amzn_nova_act_human_intervention_common.config import LoggingConfig
            >>> logger = LoggingConfig.setup_logging()
            >>> logger.info("Application started")
            2025-01-15 10:30:00,123 - amzn_nova_act_human_intervention_common - INFO - Application started

        Setup with DEBUG level and custom format::

            >>> logger = LoggingConfig.setup_logging(
            ...     level=logging.DEBUG,
            ...     format_string="%(levelname)s: %(message)s"
            ... )
            >>> logger.debug("Debugging information")
            DEBUG: Debugging information

        Get logger in your module::

            >>> logger = LoggingConfig.get_logger(__name__)
            >>> logger.info("Processing request")
        """
        if not cls._configured:
            if cls._is_lambda_environment():
                # Lambda already has logging configured, just set level
                logging.getLogger().setLevel(level)
            else:
                # Non-Lambda environment, configure from scratch
                if format_string is None:
                    format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                logging.basicConfig(level=level, format=format_string, stream=sys.stdout)

            cls._configured = True

        return logging.getLogger(logger_name)

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a logger instance.

        Parameters
        ----------
        name : str
            Logger name

        Returns
        -------
        logging.Logger
            Logger instance configured with package defaults

        Examples
        --------
        Get logger for your module::

            >>> from amzn_nova_act_human_intervention_common.config import LoggingConfig
            >>> logger = LoggingConfig.get_logger(__name__)
            >>> logger.info("Processing started")
            2025-01-15 10:30:00,123 - my_module - INFO - Processing started

        Get logger with custom name::

            >>> logger = LoggingConfig.get_logger("my_custom_logger")
            >>> logger.warning("Custom warning message")
            2025-01-15 10:30:00,456 - my_custom_logger - WARNING - Custom warning message
        """
        if not cls._configured:
            cls.setup_logging()
        return logging.getLogger(name)
