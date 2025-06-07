module.exports = {
  apps: [{
    name: "bard",
    script: "python",
    args: "app.py",
    interpreter: "none",
    env: {
      SECRET_KEY: "change-this-to-a-random-secret-key"
    },
    instances: 1,
    autorestart: true,
    watch: false
  }]
}
