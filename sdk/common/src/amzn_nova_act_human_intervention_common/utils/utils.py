"""Utility functions for the Nova Act Human Intervention Client."""

import json


class Utils:
    """General utility functions for common operations."""

    @staticmethod
    def is_valid_json(json_string: str) -> bool:
        """Check if a string is valid JSON.

        Parameters
        ----------
        json_string : str
            String to validate as JSON

        Returns
        -------
        bool
            True if the string is valid JSON, False otherwise

        Examples
        --------
        >>> Utils.is_valid_json('{"key": "value"}')
        True
        >>> Utils.is_valid_json('invalid json')
        False
        """
        try:
            json.loads(json_string)
            return True
        except json.JSONDecodeError:
            return False
