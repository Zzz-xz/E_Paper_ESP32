import argparse
import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="启动局域网墨水屏工作台")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
