package governance.authentication.context.verify.data.policy_0396

# Auto-generated policy 396
# Package: governance.authentication.context.verify.data

# Metadata
metadata := {
    "policy_id": "0396",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0396 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0396 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0396 {
    input.user.active
    input.resource.public
}
allowed_0396 {
    input.user.role == "admin"
}

# Utility function for user info
