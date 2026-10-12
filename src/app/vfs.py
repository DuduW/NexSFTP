import os


class PathEscape(Exception):
    """客户端路径越出用户根目录（含 ../ 与 symlink 逃逸）"""


def _norm(client_path: str) -> str:
    """纯词法规范化：消除 . 与 ..（不触盘，不受平台分隔符影响）。

    安全策略：任何 `..` 分量一律判越界（与 SFTP 传输面行为一致），
    不做静默折叠 —— 避免越界尝试被折叠成根目录内路径。
    """
    out = []
    for part in client_path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise PathEscape(client_path)
        out.append(part)
    return "/".join(out)


def resolve(root: str, client_path: str) -> tuple[str, str]:
    """把 SFTP 客户端路径解析为根目录内的绝对路径。

    双重防护：
    1) 词法规范化拦截 `../`、绝对路径注入；
    2) realpath 解析 symlink 后再校验前缀，拦截链接逃逸。
    返回 (真实绝对路径, 规范化相对路径)。
    """
    rel = _norm(client_path)
    target = os.path.join(root, *rel.split("/")) if rel else root
    root_real = os.path.realpath(root)
    real = os.path.realpath(target)
    if real != root_real and not real.startswith(root_real + os.sep):
        raise PathEscape(client_path)
    return real, rel
