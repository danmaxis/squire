# Ambiente para shells SSH interativos do ai-debian.
# Análogo ao Environment=PATH do unit systemd: sem isto, um humano que
# faz SSH e digita `squire run` quebra com FileNotFoundError no opencode.
export PATH=/home/ai-debian/.opencode/bin:/home/ai-debian/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH

# Runtime env (LITELLM_URL/MODEL/KEY, etc.) que o PID 1 recebeu do compose;
# shells SSH não herdam esse env, então fontamos o arquivo gerado no init.
[ -r /etc/squire.env ] && . /etc/squire.env

export SQUIRE_STATE_ROOT="${SQUIRE_STATE_ROOT:-/data}"
export SQUIRE_AGENT_REPO_ROOT="${SQUIRE_AGENT_REPO_ROOT:-/home/ai-debian/projects}"
