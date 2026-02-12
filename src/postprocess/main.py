from .postprocess import postprocess
import argparse

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-id", required=True)
    args = parser.parse_args()

    postprocess(collection_id=args.collection_id)

if __name__ == "__main__":
    main()
