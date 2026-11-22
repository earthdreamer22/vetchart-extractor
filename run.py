# -*- coding: utf-8 -*-
"""실행 파일 진입점"""
from extractor.main import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
