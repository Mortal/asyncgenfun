import functools
import itertools

async def wrap_aiter(iterable):
    for x in iterable:
        yield x

def unwrap_aiter(async_iterable):
    g = async_iterable.__aiter__()
    o = g.__anext__()
    while True:
        try:
            o.send(None)
        except StopIteration as exn:
            yield exn.args[0]
            o = g.__anext__()
        except StopAsyncIteration:
            break

def syncgenerator(async_generator_function):
    @functools.wraps(async_generator_function)
    def wrapper(iterable):
        if hasattr(iterable, '__aiter__'):
            # iterable is an async iterator => return asynchronous generator
            return async_generator_function(iterable)
        else:
            # iterable is a regular non-async iterable => return non-async generator
            return unwrap_aiter(async_generator_function(wrap_aiter(iterable)))

    return wrapper

@syncgenerator
async def count_passwords_async_iterable(async_iterable):
    count = 0
    async for line in async_iterable:
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        yield 'Username: %s' % first.split()[-1]
        yield 'Password: %s' % last.split()[0]
        count += 1
    yield 'Total number of passwords:'
    yield str(count)

@syncgenerator
async def exclaim_async_iterable(async_iterable):
    yield 'Hello world!'
    async for line in async_iterable:
        if line.endswith('!'):
            yield 'Someone yelled %r' % (line,)
        if line == 'Goodbye!':
            return

assert list(exclaim_async_iterable([])) == ['Hello world!']
assert list(count_passwords_async_iterable([])) == ['Total number of passwords:', '0']

class read_input_line:
    def __await__(self):
        return (yield None)

async def read_input_lines(sentinel):
    while True:
        line = await read_input_line()
        if line is sentinel:
            return
        yield line

def gather_processors(processor_functions, iterable):
    sentinel = object()
    processors = [p(read_input_lines(sentinel))
                  for p in processor_functions]

    iters = [processor.__aiter__() for processor in processors]
    gens = [o.__anext__() for o in iters]
    iterable = itertools.chain([None], iterable, [sentinel])
    for line in iterable:
        for i in range(len(processors)):
            if gens[i] is None:
                # Generator returned
                continue
            to_send = line
            while True:
                try:
                    gens[i].send(to_send)
                except StopIteration as exn:
                    yield i, exn.args[0]
                    to_send = None
                    gens[i] = iters[i].__anext__()
                except StopAsyncIteration:
                    gens[i] = None
                    break
                else:
                    break

processor_functions = [
    count_passwords_async_iterable,
    exclaim_async_iterable,
]

input_lines = ['Hello!',
               'First entry is foo:bar',
               'Hello again!',
               'And hello:world is the final entry',
               'Goodbye!',
               'Nice talking to you!']

for idx, line in gather_processors(processor_functions, input_lines):
    print("From %s: %s" % (processor_functions[idx].__name__, line))
