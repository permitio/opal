class PolicyRepoSettings:
    def __init__(
        self,
        local_clone_path: str | None = None,
        owner: str | None = None,
        repo_name: str | None = None,
        branch_name: str | None = None,
        repo_host: str | None = None,
        repo_port_http: int | None = None,
        repo_port_ssh: int | None = None,
        password: str | None = None,
        pat: str | None = None,
        ssh_key_path: str | None = None,
        source_repo_owner: str | None = None,
        source_repo_name: str | None = None,
        should_fork: bool = False,
        should_create_repo: bool = False,  # if True, will create the repo, if the should_fork is False.
        # If should_fork is True, it will fork and not create the repo from scratch.
        # if False, the an existing repository is expected
        webhook_secret: str | None = None,
    ):
        self.local_clone_path = local_clone_path
        self.owner = owner
        self.repo_name = repo_name
        self.branch_name = branch_name
        self.repo_host = repo_host
        self.repo_port_http = repo_port_http
        self.repo_port_ssh = repo_port_ssh
        self.password = password
        self.pat = pat
        self.ssh_key_path = ssh_key_path
        self.source_repo_owner = source_repo_owner
        self.source_repo_name = source_repo_name
        self.should_fork = should_fork
        self.should_create_repo = should_create_repo
        self.webhook_secret = webhook_secret
