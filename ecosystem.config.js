module.exports = {
    apps: [
        {
            name: "avax",
            script: "main.py",
            args: "AVAX",
            log_file: "./logs/avax.log",
            instance_var: 'INSTANCE_ID',
            interpreter: "venv/bin/python3",
            interpreter_args: "-u",
            autorestart: true,
            exp_backoff_restart_delay: 2000
        },
        {
            name: "eth",
            script: "main.py",
            args: "ETH",
            log_file: "./logs/eth.log",
            instance_var: 'INSTANCE_ID',
            interpreter: "venv/bin/python3",
            interpreter_args: "-u",
            autorestart: true,
            exp_backoff_restart_delay: 2000
        },
        {
            name: "sol",
            script: "main.py",
            args: "SOL",
            log_file: "./logs/sol.log",
            instance_var: 'INSTANCE_ID',
            interpreter: "venv/bin/python3",
            interpreter_args: "-u",
            autorestart: true,
            exp_backoff_restart_delay: 2000
        },
    ]
}
