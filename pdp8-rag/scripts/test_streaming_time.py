#!/usr/bin/env python3
"""Test streaming endpoint timing."""

import requests
import time
import json
import sys
from typing import Optional, List


def test_streaming_endpoint(
    query: str,
    base_url: str = "http://localhost:8000",
    doc_names: Optional[List[str]] = None
):
    """
    Test the streaming endpoint and measure timing.

    Args:
        query: Query to test
        base_url: Base URL of the API
        doc_names: Optional list of document names to filter
    """
    # Use doc-filtered endpoint if doc_names provided
    if doc_names:
        url = f"{base_url}/chat/stream/doc"
        params = {"message": query, "doc_names": ",".join(doc_names)}
        print(f"Using doc-filtered endpoint with doc_names: {doc_names}")
    else:
        url = f"{base_url}/chat/stream"
        params = {"message": query}

    print(f"Testing streaming endpoint with query: {query}")
    print("-" * 80)

    # Track timing
    start_time = time.time()
    first_token_time = None
    last_token_time = None
    token_count = 0
    full_answer = ""

    try:
        print(f"🔗 Connecting to: {url}")
        print(f"⏳ Waiting for response...\n")

        # Make streaming request with longer timeout
        response = requests.get(url, params=params, stream=True, timeout=300)
        response.raise_for_status()

        # Process SSE stream
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')

                # SSE format: "data: {...}"
                if line.startswith('data: '):
                    data_json = line[6:]  # Remove "data: " prefix

                    try:
                        data = json.loads(data_json)

                        if data['type'] == 'token':
                            # Track first token time
                            if first_token_time is None:
                                first_token_time = time.time()
                                time_to_first_token = first_token_time - start_time
                                print(f"\n⏱️  Time to first token: {time_to_first_token:.3f}s")
                                print("\n📝 Streaming answer:")
                                print("-" * 80)

                            # Print token
                            content = data['content']
                            print(content, end='', flush=True)
                            full_answer += content
                            token_count += 1
                            last_token_time = time.time()

                        elif data['type'] == 'metadata':
                            print("\n")
                            print("-" * 80)
                            print("\n📊 Metadata:")
                            print(f"  Strategy: {data.get('strategy')}")
                            print(f"  Strategy reasoning: {data.get('strategy_reasoning')}")
                            print(f"\n  Sources ({len(data.get('sources', []))}):")
                            for i, source in enumerate(data.get('sources', []), 1):
                                print(f"    {i}. {source.get('document')} - {source.get('page_range')}")
                                print(f"       Similarity: {source.get('similarity', 0):.4f}")

                        elif data['type'] == 'done':
                            end_time = time.time()
                            total_time = end_time - start_time
                            streaming_time = last_token_time - first_token_time if last_token_time and first_token_time else 0

                            print("\n")
                            print("-" * 80)
                            print("\n⏱️  Timing Summary:")
                            print(f"  Total time: {total_time:.3f}s")
                            print(f"  Time to first token: {first_token_time - start_time:.3f}s" if first_token_time else "  Time to first token: N/A")
                            print(f"  Streaming time: {streaming_time:.3f}s")
                            print(f"  Token count: {token_count}")
                            print(f"  Tokens per second: {token_count / streaming_time:.2f}" if streaming_time > 0 else "  Tokens per second: N/A")
                            print(f"  Answer length: {len(full_answer)} characters")

                        elif data['type'] == 'error':
                            print(f"\n❌ Error: {data.get('message')}")

                    except json.JSONDecodeError:
                        print(f"\n⚠️  Failed to parse JSON: {data_json}")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    import os
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test RAG streaming endpoint timing")
    parser.add_argument("query", nargs="*", help="Query to test (default: 'LNG power projects and development timeline')")
    parser.add_argument("--doc-names", type=str, help="Comma-separated list of document names to filter (e.g., 'pdp8,PDP8_full-with-annexes_EN')")
    parser.add_argument("--base-url", type=str, help="Base URL of the API (default: http://localhost:8000)")
    args = parser.parse_args()

    # Default query
    query = " ".join(args.query) if args.query else "LNG power projects and development timeline"

    # Parse doc_names if provided
    doc_names = None
    if args.doc_names:
        doc_names = [x.strip() for x in args.doc_names.split(",") if x.strip()]

    # Allow custom base URL from argument or environment
    base_url = args.base_url or os.getenv("API_BASE_URL", "http://localhost:8000")

    test_streaming_endpoint(query, base_url, doc_names)
