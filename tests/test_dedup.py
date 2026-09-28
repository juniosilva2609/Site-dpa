from connectors.dedup import resolver_nome


def test_arquivo_novo():
    r = resolver_nome("a.pdf", b"conteudo", {})
    assert r.nome_final == "a.pdf"
    assert r.status == "novo"


def test_arquivo_existente_mesmo_conteudo():
    r = resolver_nome("a.pdf", b"conteudo", {"a.pdf": b"conteudo"})
    assert r.nome_final == "a.pdf"
    assert r.status == "existente"


def test_arquivo_conteudo_diferente_gera_v2():
    r = resolver_nome("a.pdf", b"novo", {"a.pdf": b"velho"})
    assert r.nome_final == "a_v2.pdf"
    assert r.status == "nova_versao"


def test_v2_ja_existe_com_conteudo_diferente_gera_v3():
    existentes = {"a.pdf": b"velho", "a_v2.pdf": b"outro"}
    r = resolver_nome("a.pdf", b"novo", existentes)
    assert r.nome_final == "a_v3.pdf"
    assert r.status == "nova_versao"


def test_v2_ja_existe_com_mesmo_conteudo_e_marcado_existente():
    existentes = {"a.pdf": b"velho", "a_v2.pdf": b"novo"}
    r = resolver_nome("a.pdf", b"novo", existentes)
    assert r.nome_final == "a_v2.pdf"
    assert r.status == "existente"
