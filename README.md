
Suppose we have two **line processor** functions that take lines as input and generate lines as output:


```python
def find_passwords(iterable):
    for line in iterable:
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        yield 'Username: %s' % first.split()[-1]
        yield 'Password: %s' % last.split()[0]

def find_exclamations(iterable):
    for line in iterable:
        if line.endswith('!'):
            yield 'Someone yelled %r' % (line,)
```


```python
input_lines = ['Hello!',
               'First entry is foo:bar',
               'Hello again!',
               'And hello:world is the final entry']
```

The first line processor looks for lines containing `username:password` pairs:


```python
for line in find_passwords(input_lines):
    print(line)
```

    Username: foo
    Password: bar
    Username: hello
    Password: world


The second line processor looks for lines ending with an exclamation point:


```python
for line in find_exclamations(input_lines):
    print(line)
```

    Someone yelled 'Hello!'
    Someone yelled 'Hello again!'


Suppose we are receiving an infinite stream of lines from some source and we want to apply many such line processors simultaneously.

How would we do that?

We could replace `for line in iterable` with receiving input via the **generator protocol**:


```python
def find_passwords_gen(write_output):
    while True:
        line = yield None
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        write_output('Username: %s' % first.split()[-1])
        write_output('Password: %s' % last.split()[0])

def find_exclamations_gen(write_output):
    while True:
        line = yield None
        if line.endswith('!'):
            write_output('Someone yelled %r' % (line,))
```

Here's an example of how this protocol is used:


```python
buffer = []
processors = [
    find_passwords_gen(buffer.append),
    find_exclamations_gen(buffer.append),
]
for f in processors:
    f.send(None)  # Start the generator
for line in input_lines:
    for f in processors:
        f.send(line)
        for output_line in buffer:
            print("From %r: %s" % (f, output_line))
        del buffer[:]
```

    From <generator object find_exclamations_gen at 0x7f58a8307620>: Someone yelled 'Hello!'
    From <generator object find_passwords_gen at 0x7f58a8307048>: Username: foo
    From <generator object find_passwords_gen at 0x7f58a8307048>: Password: bar
    From <generator object find_exclamations_gen at 0x7f58a8307620>: Someone yelled 'Hello again!'
    From <generator object find_passwords_gen at 0x7f58a8307048>: Username: hello
    From <generator object find_passwords_gen at 0x7f58a8307048>: Password: world


This works, but it is unfortunate that we lost the ability to use `yield` to send output out of the line processor functions.

We will get around this by using [PEP 535 -- Asynchronous Generators](https://www.python.org/dev/peps/pep-0525/), introduced in Python 3.6. Essentially this PEP allows a function to pre-empt itself in two different ways: `yield` and `await`. We can use `await` to get the next input line and `yield` to return output lines:


```python
class read_input_line:
    def __await__(self):
        return (yield None)

async def find_passwords_async_gen():
    while True:
        line = await read_input_line()
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        yield 'Username: %s' % first.split()[-1]
        yield 'Password: %s' % last.split()[0]

async def find_exclamations_async_gen():
    while True:
        line = await read_input_line()
        if line.endswith('!'):
            yield 'Someone yelled %r' % (line,)
```


```python
processors = [
    find_passwords_async_gen,
    find_exclamations_async_gen,
]
iters = [processor().__aiter__() for processor in processors]
gens = [o.__anext__() for o in iters]
for i in range(len(processors)):
    gens[i].send(None)  # Start the generator
for line in input_lines:
    for i in range(len(processors)):
        to_send = line
        while True:
            try:
                gens[i].send(to_send)
            except StopIteration as exn:
                print("From %s: %s" % (processors[i].__name__, exn.args[0]))
                to_send = None
                gens[i] = iters[i].__anext__()
            else:
                break
```

    From find_exclamations_async_gen: Someone yelled 'Hello!'
    From find_passwords_async_gen: Username: foo
    From find_passwords_async_gen: Password: bar
    From find_exclamations_async_gen: Someone yelled 'Hello again!'
    From find_passwords_async_gen: Username: hello
    From find_passwords_async_gen: Password: world


Although the driver code is ugly, the async generators are nice! Even cooler, we can use asynchronous for-loops:


```python
async def find_passwords_async_iterable(async_iterable):
    async for line in async_iterable:
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        yield 'Username: %s' % first.split()[-1]
        yield 'Password: %s' % last.split()[0]

async def find_exclamations_async_iterable(async_iterable):
    async for line in async_iterable:
        if line.endswith('!'):
            yield 'Someone yelled %r' % (line,)
```


```python
class read_input_line:
    def __await__(self):
        return (yield None)

async def read_input_lines():
    while True:
        line = await read_input_line()
        yield line

def gather_processors(processor_functions, iterable):
    processors = [p(read_input_lines()) for p in processor_functions]

    iters = [processor.__aiter__() for processor in processors]
    gens = [o.__anext__() for o in iters]
    for i in range(len(processors)):
        gens[i].send(None)  # Start the generator
    for line in iterable:
        for i in range(len(processors)):
            to_send = line
            while True:
                try:
                    gens[i].send(to_send)
                except StopIteration as exn:
                    yield i, exn.args[0]
                    to_send = None
                    gens[i] = iters[i].__anext__()
                else:
                    break

processor_functions = [
    find_passwords_async_iterable,
    find_exclamations_async_iterable,
]

for idx, line in gather_processors(processor_functions, input_lines):
    print("From %s: %s" % (processor_functions[idx].__name__, line))
```

    From find_exclamations_async_iterable: Someone yelled 'Hello!'
    From find_passwords_async_iterable: Username: foo
    From find_passwords_async_iterable: Password: bar
    From find_exclamations_async_iterable: Someone yelled 'Hello again!'
    From find_passwords_async_iterable: Username: hello
    From find_passwords_async_iterable: Password: world


We can write some simple wrappers that convert between iterables and async iterables:


```python
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

print(list(unwrap_aiter(wrap_aiter(input_lines))))
print(list(unwrap_aiter(find_passwords_async_iterable(wrap_aiter(input_lines)))))
```

    ['Hello!', 'First entry is foo:bar', 'Hello again!', 'And hello:world is the final entry']
    ['Username: foo', 'Password: bar', 'Username: hello', 'Password: world']


Now, if we want our line processors to work both as async generators and regular generators, we can make a decorator that transparently wraps the input and unwraps the output:


```python
def syncgenerator(async_generator_function):
    def wrapper(iterable):
        if hasattr(iterable, '__aiter__'):
            # iterable is an async iterator => return asynchronous generator
            return async_generator_function(iterable)
        else:
            # iterable is a regular non-async iterable => return non-async generator
            return unwrap_aiter(async_generator_function(wrap_aiter(iterable)))

    return wrapper
```


```python
@syncgenerator
async def find_passwords_syncgen(async_iterable):
    async for line in async_iterable:
        try:
            first, last = line.split(':')
        except ValueError:
            continue
        yield 'Username: %s' % first.split()[-1]
        yield 'Password: %s' % last.split()[0]

@syncgenerator
async def find_exclamations_syncgen(async_iterable):
    async for line in async_iterable:
        if line.endswith('!'):
            yield 'Someone yelled %r' % (line,)
```

This way, we can use the functions as old-fashioned iterators:


```python
for line in find_exclamations_syncgen(input_lines):
    print(line)
```

    Someone yelled 'Hello!'
    Someone yelled 'Hello again!'


And the functions still work as asynchronous generators:


```python
processor_functions_syncgen = [
    find_passwords_syncgen,
    find_exclamations_syncgen,
]
for idx, line in gather_processors(processor_functions_syncgen, input_lines):
    print("From %s: %s" % (processor_functions[idx].__name__, line))
```

    From find_exclamations_async_iterable: Someone yelled 'Hello!'
    From find_passwords_async_iterable: Username: foo
    From find_passwords_async_iterable: Password: bar
    From find_exclamations_async_iterable: Someone yelled 'Hello again!'
    From find_passwords_async_iterable: Username: hello
    From find_passwords_async_iterable: Password: world


## The full code

The implementation below is a bit more general as it supports `yield` before/after the `async for line in iterable:` inside the asynchronous generators.


```python
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
```

    From exclaim_async_iterable: Hello world!
    From exclaim_async_iterable: Someone yelled 'Hello!'
    From count_passwords_async_iterable: Username: foo
    From count_passwords_async_iterable: Password: bar
    From exclaim_async_iterable: Someone yelled 'Hello again!'
    From count_passwords_async_iterable: Username: hello
    From count_passwords_async_iterable: Password: world
    From exclaim_async_iterable: Someone yelled 'Goodbye!'
    From count_passwords_async_iterable: Total number of passwords:
    From count_passwords_async_iterable: 2

