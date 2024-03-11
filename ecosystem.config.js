module.exports = {
    apps: [
        {
            name: "avax",
            script: "main.py",
            args: "AVAX",
            log_file: "./logs/avax.log",
            instance_var: 'INSTANCE_ID',
            autorestart: false,
            interpreter: "venv/bin/python3",
            interpreter_args: "-u"
        },
        {
            name: "eth",
            script: "main.py",
            args: "ETH",
            log_file: "./logs/eth.log",
            instance_var: 'INSTANCE_ID',
            autorestart: false,
            interpreter: "venv/bin/python3",
            interpreter_args: "-u"
        },
        {
            name: "sol",
            script: "main.py",
            args: "SOL",
            log_file: "./logs/sol.log",
            instance_var: 'INSTANCE_ID',
            autorestart: false,
            interpreter: "venv/bin/python3",
            interpreter_args: "-u"
        },
    ]
}
