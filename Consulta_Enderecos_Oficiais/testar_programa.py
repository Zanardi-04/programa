# Testes locais rápidos: execute com `python testar_programa.py`.
import json
import consulta_enderecos as app

records = app.parse_records()
with open(app.OFFICIALS_FILE, encoding='utf-8') as f:
    officials = json.load(f)

cases = [
    ('Alameda Dalton Barreto, nº 13, aptº 101', '6'),
    ('Rua Silvia Pozzano nº 3003, bloco 08, apt. 703', '39'),
    ('Avenida das Américas, nº 10.017', '22'),
    ('Avenida das Américas, nº 8.152', '22'),
    ('Avenida das Américas, nº 5.300', '19'),
    ('Avenida das Américas, 19001', '39'),
    ('Avenida Gilka Machado, n° 885, Apartamento 302', '7'),
    ('Avenida Lúcio Costa, 18000, apt 202', '7'),
]
for address, expected in cases:
    result = app.lookup(address, records, officials)
    got = {str(x['listing']) for x in result['results']}
    assert result['status'].startswith('Localizado'), (address, result)
    assert got == {expected}, (address, expected, got, result['status'])

# Casos que antes geravam falso positivo por correspondência de pedaço de palavra.
for address in ('Alameda Dalton Barreto, nº 13', 'Rua Silvia Pozzano nº 3003', 'Avenida das Américas, 10017'):
    result = app.lookup(address, records, officials)
    assert all(x.get('street') not in ('A', 'A (Cond Prq Nobre)') for x in result['results']), (address, result)

print(f'OK: {len(records)} registros lidos; {len(cases)} endereços de teste passaram; falsos positivos básicos não encontrados.')

# Busca tolerante a palavra extra e erro de grafia (caso apontado pelo usuário).
result = app.lookup('Rua Professor Silvio Elia, 47, casa 46', records, officials)
got = {(str(x['listing']), x['street'], x['area'], x['official']) for x in result['results']}
assert ('29', 'Silvio Elia', 'Vargem Pequena', 'Maria Celeste') in got, ('Professor Silvio Elia', result)

# Variações de título, acento e pequena diferença de escrita devem continuar encontrando a rua.
for address in ('R. Professor Sílvio Elia, 47, casa 46', 'Silvio Elia 47', 'Rua Silvio Elia, nº 47, Casa 46'):
    result = app.lookup(address, records, officials)
    got = {(str(x['listing']), x['street'], x['area'], x['official']) for x in result['results']}
    assert ('29', 'Silvio Elia', 'Vargem Pequena', 'Maria Celeste') in got, (address, result)


# Casos de regressão: a regra de faixa deve selecionar a listagem correta.
for address, expected_listing, expected_area in [
    ('AVENIDA DAS AMERICAS, N° 3959', '20', 'Midtown'),
    ('AVENIDA AYRTON SENNA, N° 5555', '31', 'Barra Dor'),
]:
    result = app.lookup(address, records, officials)
    assert result['status'].startswith('Localizado'), (address, result)
    assert len(result['results']) == 1, (address, result)
    assert str(result['results'][0]['listing']) == expected_listing, (address, result)
    assert result['results'][0]['area'] == expected_area, (address, result)

print('OK: regras de faixa/paridade selecionam automaticamente as duas listagens esperadas.')

# Regressão: Estrada dos Bandeirantes 11605 é ímpar e cai na faixa 8903–13907 do nº 12.
result = app.lookup('Estrada dos Bandeirantes, nº 11605 23B', records, officials)
assert result['status'].startswith('Localizado'), ('Estrada dos Bandeirantes 11605', result)
assert len(result['results']) == 1, ('Estrada dos Bandeirantes 11605', result)
assert str(result['results'][0]['listing']) == '12', ('Estrada dos Bandeirantes 11605', result)
assert result['results'][0]['area'] == 'Vargem Pequena', ('Estrada dos Bandeirantes 11605', result)

# Regressão: exceções incluídas por "mais" devem ser reconhecidas mesmo fora da faixa-base.
for address, expected in [
    ('DAS AMERICAS, 17701, SAL 0203', '38'),
    ('Avenida das Américas, 17485', '38'),
    ('Avenida das Américas, 17655', '38'),
    ('Avenida das Américas, 17145', '38'),
]:
    result = app.lookup(address, records, officials)
    got = {str(x['listing']) for x in result['results']}
    assert result['status'].startswith('Localizado'), (address, result)
    assert got == {expected}, (address, expected, got, result)

print('OK: exceções numéricas explícitas da Avenida das Américas selecionam a listagem 38.')


# Regressão obrigatória: a regra PAR/ÍMPAR deve ser preservada, exibida e aplicada.
armando_records = [r for r in records if 'armando lombardi' in app.norm(r['clean_name'])]
assert len(armando_records) == 2, ('Armando Lombardi deveria ter dois registros', armando_records)
rule_by_listing = {str(r['listing']): app.norm(r['rule']) for r in armando_records}
assert rule_by_listing.get('6') == 'par', ('A regra PAR da listagem 6 não foi preservada', rule_by_listing)
assert rule_by_listing.get('8') == 'impar', ('A regra ÍMPAR da listagem 8 não foi preservada', rule_by_listing)

result = app.lookup('Avenida Armando Lombardi, 400', records, officials)
assert result['status'].startswith('Localizado'), ('Nº 400 deveria ser localizado sem ambiguidade', result)
assert len(result['results']) == 1, ('Nº 400 deveria retornar uma única listagem', result)
assert str(result['results'][0]['listing']) == '6', ('Nº 400 deveria selecionar a listagem 6', result)
assert app.norm(result['results'][0]['rule']) == 'par', ('A regra PAR precisa continuar visível no resultado', result)
assert result['results'][0]['area'] == 'Perto Igreja da Barra', ('Área incorreta para o nº 400', result)

result = app.lookup('Avenida Armando Lombardi, 401', records, officials)
assert result['status'].startswith('Localizado'), ('Nº 401 deveria ser localizado sem ambiguidade', result)
assert len(result['results']) == 1, ('Nº 401 deveria retornar uma única listagem', result)
assert str(result['results'][0]['listing']) == '8', ('Nº 401 deveria selecionar a listagem 8', result)
assert app.norm(result['results'][0]['rule']) == 'impar', ('A regra ÍMPAR precisa continuar visível no resultado', result)

result = app.lookup('Avenida Armando Lombardi', records, officials)
shown_rules = {str(x['listing']): app.norm(x['rule']) for x in result['results']}
assert shown_rules.get('6') == 'par' and shown_rules.get('8') == 'impar', (
    'Sem número, as duas alternativas devem exibir suas regras', result)
print('OK: regras PAR/ÍMPAR são preservadas, exibidas e selecionam a listagem correta.')

# Regressão: exceções numéricas explícitas da Avenida das Américas não podem
# ser perdidas nem absorvidas por uma faixa geral da mesma avenida.
for address, expected in [
    ('Avenida das Américas, 7380', '22'),      # exceção fora da faixa par anterior
    ('Avenida das Américas, 1245', '20'),      # inclusão na regra de outra faixa
    ('Avenida das Américas, 2500', '37'),      # inclusão fora da faixa-base
    ('Avenida das Américas, 3301', '37'),
    ('Avenida das Américas, 3501', '37'),
    ('Avenida das Américas, 1917', '37'),      # excluído de uma seção e incluído na seguinte
    ('Avenida das Américas, 17145', '38'),
    ('Avenida das Américas, 17485', '38'),
    ('Avenida das Américas, 17655', '38'),
    ('Avenida das Américas, 17701', '38'),
    ('Avenida das Américas, 19001', '39'),     # excluído da listagem 38 e incluído na 39
]:
    result = app.lookup(address, records, officials)
    got = {str(x['listing']) for x in result['results']}
    assert result['status'].startswith('Localizado'), (address, result)
    assert got == {expected}, (address, expected, got, result)

print('OK: exceções e transições de seção da Avenida das Américas preservadas.')

# Regressão: variações do nome oficial não podem excluir seções da Avenida
# Prefeito Dulcídio Cardoso; listas pontuais têm prioridade sobre faixas amplas.
for address, expected in [
    ('Avenida Prefeito Dulcídio Cardoso, 120', '22'),
    ('Avenida Prefeito Dulcídio Cardoso, 139', '6'),
    ('Avenida Prefeito Dulcídio Cardoso, 200', '28'),
    ('Avenida Prefeito Dulcídio Cardoso, 271', '6'),
    ('Avenida Prefeito Dulcídio Cardoso, 315', '6'),
    ('Avenida Prefeito Dulcídio Cardoso, 350', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 380', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 502', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 800', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 1120', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 19', '20'),
    ('Avenida Prefeito Dulcídio Cardoso, 521', '22'),
    ('Avenida Prefeito Dulcídio Cardoso, 4252', '37'),
    ('Avenida Prefeito Dulcídio Cardoso, 2901', '19'),
    ('Avenida Prefeito Dulcídio Cardoso, 3042', '21'),
    ('Avenida Prefeito Dulcídio Cardoso, 5000', '28'),
    ('Avenida Prefeito Dulcídio Cardoso, 10900', '22'),
    ('Avenida Prefeito Dulcídio Cardoso, 11000', '22'),
    ('Avenida Prefeito Dulcídio Cardoso, 11100', '22'),
]:
    result = app.lookup(address, records, officials)
    got = {str(x['listing']) for x in result['results']}
    assert result['status'].startswith('Localizado'), (address, result)
    assert got == {expected}, (address, expected, got, result)

# Confirma que as formas com e sem título final foram unificadas.
assert app.canonical_street('Avenida Prefeito Dulcídio Cardoso') == 'dulcidio cardoso'
assert app.canonical_street('Dulcídio Cardoso, Prefeito') == 'dulcidio cardoso'
print('OK: exceções de Dulcídio Cardoso priorizadas e nomes equivalentes normalizados.')
