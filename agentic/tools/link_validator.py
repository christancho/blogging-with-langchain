"""
Link Validator Tool for validating URL accessibility
"""
import subprocess
from typing import Dict, List, Tuple
from urllib.parse import urlparse
from config import Config


class LinkValidatorTool:
    """
    Tool for validating URLs by checking HTTP status codes.
    Uses curl with HEAD requests for fast validation without downloading content.
    """

    def validate_url(self, url: str) -> Dict[str, any]:
        """
        Validate a single URL by checking its HTTP status code.

        Args:
            url: The URL to validate

        Returns:
            Dictionary with validation results:
            {
                "url": str,
                "is_valid": bool,
                "status_code": int or None,
                "error": str or None
            }
        """
        try:
            # Use curl with HEAD request to check status without downloading content
            # -I: HEAD request only
            # -L: Follow redirects
            # -s: Silent mode
            # -o /dev/null: Discard output
            # -w "%{http_code}": Write out only the HTTP status code
            # --max-time: Timeout
            result = subprocess.run(
                [
                    'curl',
                    '-I',  # HEAD request
                    '-L',  # Follow redirects
                    '-s',  # Silent
                    '-o', '/dev/null',  # Discard output
                    '-w', '%{http_code}',  # Write HTTP code
                    '--max-time', str(Config.URL_FETCH_TIMEOUT),
                    url
                ],
                capture_output=True,
                text=True,
                timeout=Config.URL_FETCH_TIMEOUT + 5
            )

            if result.returncode == 0 and result.stdout:
                status_code = int(result.stdout.strip())

                # Consider 2xx and 3xx as valid (3xx should be followed by -L)
                is_valid = 200 <= status_code < 400

                return {
                    "url": url,
                    "is_valid": is_valid,
                    "status_code": status_code,
                    "error": None if is_valid else f"HTTP {status_code}"
                }
            else:
                # curl failed (timeout, connection error, etc.)
                return {
                    "url": url,
                    "is_valid": False,
                    "status_code": None,
                    "error": "Connection failed or timeout"
                }

        except subprocess.TimeoutExpired:
            return {
                "url": url,
                "is_valid": False,
                "status_code": None,
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "url": url,
                "is_valid": False,
                "status_code": None,
                "error": str(e)
            }

    def validate_urls(self, urls: List[str], show_progress: bool = True) -> Tuple[List[str], List[Dict]]:
        """
        Validate a list of URLs and return valid ones.

        Args:
            urls: List of URLs to validate
            show_progress: Whether to print validation progress

        Returns:
            Tuple of (valid_urls, validation_results):
            - valid_urls: List of URLs that passed validation
            - validation_results: List of all validation result dicts
        """
        if not urls:
            return [], []

        if show_progress:
            print(f"\n🔗 Validating {len(urls)} URLs...")

        valid_urls = []
        validation_results = []

        for idx, url in enumerate(urls, 1):
            result = self.validate_url(url)
            validation_results.append(result)

            if result["is_valid"]:
                valid_urls.append(url)
                if show_progress:
                    print(f"   [{idx}/{len(urls)}] ✓ {url[:70]}...")
            else:
                if show_progress:
                    error_msg = result["error"] or f"HTTP {result['status_code']}"
                    print(f"   [{idx}/{len(urls)}] ✗ {url[:70]}... ({error_msg})")

        if show_progress:
            print(f"\n✓ Validation complete: {len(valid_urls)}/{len(urls)} URLs valid")
            if len(valid_urls) < len(urls):
                print(f"⚠️  Filtered out {len(urls) - len(valid_urls)} broken/invalid URLs")

        return valid_urls, validation_results

    def validate_urls_batch(
        self,
        urls: List[str],
        batch_size: int = 10,
        show_progress: bool = True
    ) -> Tuple[List[str], List[Dict]]:
        """
        Validate URLs in batches for better performance with many URLs.

        Args:
            urls: List of URLs to validate
            batch_size: Number of URLs to validate in parallel (not implemented yet, sequential for now)
            show_progress: Whether to print validation progress

        Returns:
            Tuple of (valid_urls, validation_results)
        """
        # For now, just call validate_urls
        # Future enhancement: implement parallel validation with threading
        return self.validate_urls(urls, show_progress)

    def get_validation_summary(self, validation_results: List[Dict]) -> Dict[str, any]:
        """
        Generate a summary of validation results.

        Args:
            validation_results: List of validation result dicts

        Returns:
            Summary dictionary with statistics
        """
        total = len(validation_results)
        valid = sum(1 for r in validation_results if r["is_valid"])
        invalid = total - valid

        # Count error types
        error_types = {}
        for result in validation_results:
            if not result["is_valid"]:
                error = result.get("error") or f"HTTP {result.get('status_code')}"
                error_types[error] = error_types.get(error, 0) + 1

        return {
            "total_urls": total,
            "valid_urls": valid,
            "invalid_urls": invalid,
            "success_rate": (valid / total * 100) if total > 0 else 0,
            "error_breakdown": error_types
        }
