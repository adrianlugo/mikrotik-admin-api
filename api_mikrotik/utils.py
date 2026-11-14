import re

def convertir_rate_limit_a_mbps(rate_limit, subida_default=5, bajada_default=10):
    """
    Convierte un string de rate-limit de MikroTik (ej. '5M/10M', '512k/1M') 
    a valores enteros de subida y bajada en Mbps.
    """
    subida, bajada = subida_default, bajada_default
    if not rate_limit or '/' not in rate_limit:
        return subida, bajada

    def a_mbps(valor):
        coincidencia = re.fullmatch(r'(\d+(?:\.\d+)?)([kmgt]?)(?:bps)?', valor.strip().lower())
        if not coincidencia:
            return None
        numero, unidad = float(coincidencia.group(1)), coincidencia.group(2)
        factores = {'': 1 / 1000000, 'k': 1 / 1000, 'm': 1, 'g': 1000, 't': 1000000}
        resultado = numero * factores[unidad]
        return max(1, int(resultado))

    partes = rate_limit.split('/', 1)
    upload = a_mbps(partes[0])
    download = a_mbps(partes[1])
    if upload is not None:
        subida = upload
    if download is not None:
        bajada = download
    return subida, bajada