import json
import re


BINDING_LEFT = 0
BINDING_RIGHT = 1
DROP_DELIMITERS = 2


class ParseFailed(Exception):

	def __init__(self, block):
		r = block.root
		self.position = min(len(r.original_tokens) - 1, r.rightmost)
		self.location = r.original_tokens[self.position]['position']

	def __str__(self):
		return 'Failed to parse token at position {}'.format(self.position)


class UnableToFinishParsing(ParseFailed): pass
class UnexpectedLackOfToken(ParseFailed): pass
class ImbalancedBraces(Exception): pass


class TokenizationFailed(Exception):

	def __init__(self, position):
		self.position = position


class TokenRoot:

	''' Class that contains a list of tokens '''

	def __init__(self, string, original_tokens, nested_tokens):
		self.string = string
		self.rightmost = -1
		self.original_tokens = original_tokens
		self.tokens = self.process_nested_tokens(nested_tokens)

	def update_rightmost(self, position):
		self.rightmost = max(self.rightmost, position)

	def process_nested_tokens(self, tokens):
		for i in range(len(tokens)):
			if isinstance(tokens[i], list):
				tokens[i] = self.process_nested_tokens(tokens[i])
		return TokenBlock(self, tokens)


class TokenBlock:

	def __init__(self, root, values):
		self.place = 0
		self.values = values
		self.root = root

	def __getitem__(self, index):
		if self.place + index < len(self.values):
			token = self.values[self.place + index]
			if isinstance(token, TokenBlock):
				return token
			return token['string']

	def eat(self):
		self.place += 1
		token = self.values[self.place - 1]
		if isinstance(token, TokenBlock):
			return token
		else:
			self.root.update_rightmost(token['position'])
			return token['string']

	def eat_details(self):
		self.place += 1
		token = self.values[self.place - 1]
		if not isinstance(token, TokenBlock):
			self.root.update_rightmost(token['position'])
		return token

	def details(self, index = 0):
		if self.place + index < len(self.values):
			return self.values[self.place + index]

	def peek(self, index, *valids):
		if self.place + index < len(self.values):
			t = self.values[self.place + index]
			if isinstance(t, dict):
				return t['#'] in valids

	def is_complete(self):
		return self.place >= len(self.values)


def ensure_completed(function, tokens):
	result = function(tokens)
	if not tokens.is_complete():
		raise UnableToFinishParsing(tokens)
	return result


def eat_delimited(subrule, delimiters, binding, type, allow_nothing = False, always_package = False):
	def internal(tokens):
		listing = []
		if tokens.is_complete():
			if not allow_nothing:
				raise UnexpectedLackOfToken(tokens)
		else:
			listing = [subrule(tokens)]
		while tokens.peek(0, *delimiters):
			listing.append(tokens.eat_details())
			listing.append(subrule(tokens))
		if len(listing) == 1 and not always_package:
			return listing[0]
		if binding == BINDING_LEFT:
			listing = list(listing[::-1])
			value = listing.pop()
			while listing:
				delimiter = listing.pop()
				right = listing.pop()
				value = {
					'#': type,
					'operator': delimiter['string'],
					'left': value,
					'right': right,
					'token': delimiter
				}
			return value
		elif binding == BINDING_RIGHT:
			value = listing.pop()
			while listing:
				delimiter = listing.pop()
				left = listing.pop()
				value = {
					'#': type,
					'operator': delimiter['string'],
					'left': left,
					'right': value,
					'token': delimiter
				}
			return value
		elif binding == DROP_DELIMITERS:
			return {
				'#': type,
				'items': listing[::2]
			}
		else:
			raise ValueError
	internal.__name__ = 'eat_delimited___' + type
	return internal


def atom(tokens):
	if tokens.peek(0, 'number', 'word'):
		return tokens.eat_details()


def word(tokens):
	if tokens.peek(0, 'word'):
		return tokens.eat_details()


def wrapped_expression(tokens):
	if isinstance(tokens[0], TokenBlock):
		return ensure_completed(expression, tokens.eat())
	return atom(tokens)


def expect(tokens, symbol):
	assert tokens[0] == symbol
	return tokens.eat()


def function_call(tokens):
	value = wrapped_expression(tokens)
	calls = []
	while isinstance(tokens.details(), TokenBlock):
		calls.append(ensure_completed(argument_list, tokens.eat()))
	calls = calls[::-1]
	while calls:
		value = {
			'#': 'function_call',
			'function': value,
			'arguments': calls.pop()
		}
	return value


def logic_not(tokens):
	if tokens.peek(0, 'bang'):
		tokens.eat()
		return {
			'#': 'not',
			'expression': logic_not(tokens)
		}
	return function_call(tokens)


def factorial(tokens):
	value = logic_not(tokens)
	while tokens[0] == '!':
		tokens.eat()
		value = {'#': 'factorial', 'value': value}
	return value


def dieroll(tokens):
	if tokens[0] == 'd':
		tokens.eat()
		return {
			'#': 'die',
			'faces': factorial(tokens)
		}
	left = factorial(tokens)
	if tokens[0] == 'd':
		tokens.eat()
		return {
			'#': 'die',
			'times': left,
			'faces': factorial(tokens)
		}
	return left


SUPERSCRIPT_MAP = {
	ord('⁰'): '0',
	ord('¹'): '1',
	ord('²'): '2',
	ord('³'): '3',
	ord('⁴'): '4',
	ord('⁵'): '5',
	ord('⁶'): '6',
	ord('⁷'): '7',
	ord('⁸'): '8',
	ord('⁹'): '9'
}

def superscript(tokens):
	result = dieroll(tokens)
	while tokens.peek(0, 'superscript'):
		tok = tokens.eat_details()
		print(tok['string'], tok['string'].translate(SUPERSCRIPT_MAP))
		result = {
			'#': 'bin_op',
			'operator': '^',
			'left': result,
			'right': {
				'#': 'number',
				'string': tok['string'].translate(SUPERSCRIPT_MAP),
				'position': tok['position']
			}
		}
	return result


def expression(tokens):
	return function_definition(tokens)


_parameter_list = eat_delimited(word, ['comma'], DROP_DELIMITERS, 'parameters', allow_nothing = True, always_package = True)

def parameter_list(tokens):
	params = _parameter_list(tokens)
	is_variadic = False
	if tokens.peek(0, 'period'):
		is_variadic = True
		tokens.eat()
	return params, is_variadic


argument_list = eat_delimited(expression, ['comma'], DROP_DELIMITERS, 'parameters', allow_nothing = True, always_package = True)

def uminus2(tokens):
	if tokens[0] == '-':
		tokens.eat()
		return {
			'#': 'uminus',
			'value': uminus2(tokens)
		}
	return superscript(tokens)


power     = eat_delimited(uminus2,    ['pow_op'],  BINDING_RIGHT, 'bin_op')

def uminus(tokens):
	if tokens[0] == '-':
		tokens.eat()
		return {
			'#': 'uminus',
			'value': uminus(tokens)
		}
	return power(tokens)

# power     = eat_delimited(uminus,    ['pow_op'],  BINDING_RIGHT, 'bin_op')
modulo    = eat_delimited(uminus,     ['mod_op'],  BINDING_LEFT,  'bin_op')
product   = eat_delimited(modulo,    ['mul_op'],  BINDING_LEFT,  'bin_op')
addition  = eat_delimited(product,   ['add_op'],  BINDING_LEFT,  'bin_op')
logic_and = eat_delimited(addition,  ['land_op'], BINDING_LEFT,  'bin_op')
logic_or  = eat_delimited(logic_and, ['lor_op'],  BINDING_LEFT,  'bin_op')


def comparison_list(tokens):
	result = logic_or(tokens)
	if result and tokens.peek(0, 'comp_op'):
		result = {
			'#': 'comparison',
			'first': result,
			'rest': [],
		}
		while tokens.peek(0, 'comp_op'):
			operator = tokens.eat()
			value = logic_or(tokens)
			result['rest'].append({
				'operator': operator,
				'value': value
			})
	return result


def function_definition(tokens):
	if tokens.peek(1, 'function_definition'):
		if not isinstance(tokens[0], TokenBlock):
			raise ParseFailed(tokens)
		args, is_variadic = ensure_completed(parameter_list, tokens.eat_details())
		kind = tokens.eat_details()
		expr = expression(tokens)
		return {
			'#': 'function_definition',
			'parameters': args,
			'kind': kind['string'],
			'expression': expr,
			'variadic': is_variadic,
			'token': kind
		}
	return comparison_list(tokens)


def statement(tokens):
	if tokens.peek(1, 'assignment'):
		name = word(tokens)
		tokens.eat()
		value = expression(tokens)
		return {
			'#': 'assignment',
			'variable': name,
			'value': value
		}
	return expression(tokens)


program = eat_delimited(statement, ['comma'], DROP_DELIMITERS, 'program')


def process_tokens(tokens):
	# Check that the brackets are balanced
	depth = 0
	for tok in tokens:
		if tok['string'] == '(':
			depth += 1
		elif tok['string'] == ')':
			depth -= 1
			if depth < 0:
				raise ImbalancedBraces
	if depth > 0:
		raise ImbalancedBraces
	# Do the thing
	tokens = tokens[::-1]
	def recurse():
		result = []
		while tokens:
			tok = tokens.pop()
			if tok['string'] == '(':
				result.append(recurse())
			elif tok['string'] == ')':
				break
			else:
				result.append(tok)
		return result
	return recurse()


def run(string):
	tokens = parse(string)[1]
	try:
		result = ensure_completed(program, tokens.tokens)
	except ParseFailed as e:
		print('Parsing failed:')
		print(string)
		print(' ' * e.position + '^')
	else:
		print(result)
		print(json.dumps(result, indent = 4))


def run_script(module):
	filename = 'calculator/scripts/{}.c5'.format(module)
	with open(filename) as f:
		data = f.read()
	data = data.replace('\n', ' ')
	return run(data)


def tokenizer(original_string, ttypes, source_name = '__unknown__'):
	# print(string)
	regexes = [x if len(x) == 3 else (x[0], x[1], None) for x in ttypes]
	regexes = list(map(lambda x: (x[0], re.compile(x[1]), x[2]), regexes))
	result = []
	# Hard coded thing here, maybe remove it.
	string = original_string.replace('\t', ' ')
	location = 0
	while len(string) > 0:
		if string[0] in ' \n':
			string = string[1:]
			location += 1
		else:
			possible = []
			for name, cre, replacement in regexes:
				# print(i)
				match = cre.match(string)
				if match is not None:
					possible.append((name, replacement or match.group()))
			possible.sort(key = lambda x: len(x[1]), reverse = True)
			# print(possible)
			if len(possible) == 0:
				raise TokenizationFailed(location)
				# raise TokenizationFailed(original_string, len(original_string) - len(string))
			# print(possible[0][1])
			if possible[0][0] != '__remove__':
				result.append({
					'#': possible[0][0],
					'string': possible[0][1],
					'position': location,
					'source': {
						'name': source_name,
						'code': original_string,
						'position': location
					}
				})
			location += len(possible[0][1])
			string = string[len(possible[0][1]):]
	return result


if __name__ == '__main__':
	# run('1 + 2')
	# run('( ) -> 4')
	run_script('c6')
	run_script('sayaks')
	# line = input('> ')
	# while line != '':
	# 	run(line)
	# 	line = input('> ')


def parse(string, source_name = '__unknown__'):
	tokens = tokenizer(
		string,
		[
			('__remove__', r'#.*'),
			('number', r'\d*\.?\d+([eE]-?\d+)?i?'),
			('word', r'π|[d][a-zA-Z_][a-zA-Z0-9_]*|[abce-zA-Z_][a-zA-Z0-9_]*'),
			('die_op', r'd'),
			('pow_op', r'\^'),
			('superscript', r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+'),
			('mod_op', r'\%'),
			('mul_op', r'[/÷]', '/'),
			('mul_op', r'[*×]', '*'),
			('add_op', r'[+-]'),
			# ('comp_op', r'<=|>='),
			('comp_op', r'<=|>=|<|>|!=|=='),
			('paren', r'[()]'),
			('function_definition', r'~>|->'),
			('comma', r','),
			('assignment', r'='),
			('land_op', r'&'),
			('lor_op', r'\|'),
			('bang', r'!'),
			('period', r'\.')
		],
		source_name = source_name
	)
	nested = process_tokens(tokens)
	package = TokenRoot(string, tokens, nested)
	result = ensure_completed(program, package.tokens)
	return package, result
