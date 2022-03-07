# python-dos
Async multiprocess DOS tool

.. image:: https://github.com/ride90/python-dos/raw/master/demo.png

## Install dependencies
```shell
pip install -r requirements.txt
```

## How to use
### Get help
```shell
python  dos.py --help
```

### Example
```shell
python dos.py --url=https://github.com --method=RANDOM --proc-num=4 --req-num=100
```
:warning: DON'T SEND REQUESTS TO `https://github.com`!


### TODO
- Rotate VPN after X requests
- Add asyncio semaphore
- Tweak TCPConnector
