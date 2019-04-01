import re
import youtube_dl
import asyncio
import aiohttp
import ffmpy3
import os
import argparse
import sys
from hurry.filesize import size

ydl_opts = {'quite': True}


def parse_audio_url(video_info):
    highest_quality = {}
    for format_ in video_info['formats']:
        if 'audio only' in format_['format'] and format_['ext'] == 'webm':
            try:
                if 'filesize' not in highest_quality:
                    highest_quality = format_
                elif format_['filesize'] > highest_quality['filesize']:
                    highest_quality = format_
            except TypeError:
                highest_quality = format_

    if not highest_quality:
        print('Cannot download: {} audio url not found'.format(
            video_info['title']))
        return None

    highest_quality['title'] = video_info['title']
    return highest_quality


def get_list_videos_url(playlist_url):
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        resp = ydl.extract_info(url, download=False)
        return resp


async def convert_to_mp3(input_filename, output_filename):
    print('start converting {}'.format(input_filename))
    ff = ffmpy3.FFmpeg(
        inputs={input_filename: None},
        outputs={output_filename: None},
        global_options=['-y'])
    await ff.run_async(stderr=asyncio.subprocess.PIPE)
    await ff.wait()
    print('sucessfully converting {} to mp3'.format(input_filename))
    os.remove(input_filename)
    return output_filename


async def fetch_url(output_dir, url, session):
    total_size = url['filesize']
    current_size = 0
    chunk_size = 1024 * 100
    async with session.get(url['url'], timeout=None) as resp:
        filename = '{}/{}.{}'.format(output_dir, url['title'], url['ext'])
        print('start downloading {}'.format(url['title']))
        with open(filename, 'wb') as f:
            async for data in resp.content.iter_chunked(chunk_size):
                current_size += sys.getsizeof(data)
                mystring = 'Download {}: {} from {}'.format(
                    url['title'], size(current_size), size(total_size))
                print(mystring, end='\r', flush=True)
                f.write(data)
            print()

    print('sucessfully download {}'.format(url['title']))
    return filename


async def process_download(output_dir, url, session):
    webm_file = await fetch_url(output_dir, url, session)
    mp3_file = await convert_to_mp3(webm_file, '{}/{}.mp3'.format(
        output_dir, url['title']))
    return mp3_file


async def download_audio(output_dir, urls):
    async with aiohttp.ClientSession() as session:
        tasks = [process_download(output_dir, url, session) for url in urls]
        return await asyncio.gather(*tasks)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def main(output_dir, urls):
    loop = asyncio.get_event_loop()
    final_result = []
    for chunked_urls in chunks(urls, 5):
        results = loop.run_until_complete(
            download_audio(output_dir, chunked_urls))
        for result in results:
            final_result.append(result)

    return final_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser('Youtube mp3 downloader')
    parser.add_argument('--url', help='youtube url')
    parser.add_argument('--output-dir', help='output directory')
    args = parser.parse_args()

    if args.url is not None:
        url = args.url
        result = get_list_videos_url(url)
        if 'entries' in result:
            result = result['entries']
        else:
            result = [result]

        audio_urls = []
        for video_info in result:
            audio_url = parse_audio_url(video_info)
            if audio_url is not None:
                audio_urls.append(audio_url)

        if args.output_dir is not None:
            output_dir = args.output_dir
        else:
            output_dir = os.path.abspath('.')

        if output_dir.endswith('/'):
            output_dir = re.sub(r'\/$', '', output_dir)

        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        result = main(output_dir, audio_urls)
    else:
        parser.print_help()
