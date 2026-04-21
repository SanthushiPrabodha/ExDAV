"""
Small helper script for showcase demo runs.

Usage:
    python demo/run_demo.py --image "path/to/image.jpg"
"""

import argparse
import json

from src.pipeline.run_pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run Ex-DAV showcase demo")
    parser.add_argument("--image", required=True, help="Path to demo image")
    args = parser.parse_args()

    result = run_pipeline(args.image)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
