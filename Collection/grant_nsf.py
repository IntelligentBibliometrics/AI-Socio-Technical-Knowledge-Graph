import argparse
import logging
import time
import zipfile
from pathlib import Path

import requests

DOWNLOAD_URL = "https://www.nsf.gov/awardsearch/download"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nsf")


def create_directories(base_dir):
    output_dir = Path(base_dir)
    zip_dir = output_dir / "zip"
    data_dir = output_dir / "outputdata"
    for d in (output_dir, zip_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)
    return zip_dir, data_dir


def check_file_exists(zip_path, data_path):
    zip_exists = zip_path.exists() and zip_path.stat().st_size > 0
    data_exists = data_path.exists() and any(data_path.iterdir())
    return zip_exists, data_exists


def download_one(name, url, zip_path, data_path):
    zip_exists, data_exists = check_file_exists(zip_path, data_path)
    if zip_exists and data_exists:
        log.info("[%s] 已存在, 跳过下载", name)
        return zip_path, True
    if zip_exists and not data_exists:
        log.info("[%s] zip 已存在, 仅需解压", name)
        return zip_path, False

    log.info("[%s] 正在下载...", name)
    try:
        with requests.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        log.info("[%s] 下载完成", name)
        return zip_path, False
    except requests.exceptions.RequestException as e:
        log.error("[%s] 下载失败: %s", name, e)
        return None, False


def extract_zip(zip_path, data_dir, folder_name=None):
    if not zip_path or not zip_path.exists():
        return False
    folder_name = folder_name or zip_path.stem
    extract_path = data_dir / folder_name
    if extract_path.exists() and any(extract_path.iterdir()):
        log.info("[%s] 已解压, 跳过", folder_name)
        return True
    extract_path.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        log.info("[%s] 解压完成", folder_name)
        return True
    except zipfile.BadZipFile as e:
        log.error("[%s] 解压失败: %s", folder_name, e)
        return False


def main():
    ap = argparse.ArgumentParser(description="下载 NSF 公开 Award 数据 (无需密钥)。")
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "output"),
                    help="输出目录 (默认: 脚本旁的 ./output)")
    ap.add_argument("--start-year", type=int, default=1976, help="起始年 (默认 1976)")
    ap.add_argument("--end-year", type=int, default=2025, help="结束年 (默认 2025)")
    args = ap.parse_args()

    zip_dir, data_dir = create_directories(args.outdir)
    total = 1 + (args.end_year - args.start_year + 1)
    log.info("NSF 下载 | 年份 %d-%d | 共 %d 个文件 | 输出 %s",
             args.start_year, args.end_year, total, args.outdir)

    hist_url = "%s?DownloadFileName=Historical&All=true&isJson=true" % DOWNLOAD_URL
    hist_zip, already = download_one("Historical", hist_url,
                                     zip_dir / "Historical.zip", data_dir / "Historical_pre1976")
    if hist_zip and not already:
        extract_zip(hist_zip, data_dir, "Historical_pre1976")
    time.sleep(1)

    for year in range(args.start_year, args.end_year + 1):
        url = "%s?DownloadFileName=%d&All=true&isJson=true" % (DOWNLOAD_URL, year)
        zip_path, already = download_one(str(year), url, zip_dir / ("%d.zip" % year), data_dir / str(year))
        if zip_path and not already:
            extract_zip(zip_path, data_dir)
        time.sleep(0.5)

    log.info("全部完成。zip -> %s | 解压数据 -> %s", zip_dir, data_dir)


if __name__ == "__main__":
    main()
