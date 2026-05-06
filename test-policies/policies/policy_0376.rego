package governance.authorization.resource.check.policy_0376

# Auto-generated policy 376
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0376",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0376 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0376 {
    input.user.role == "admin"
}
approved_0376 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0376 {
    input.user.active
    input.resource.public
}

# Utility function for user info
