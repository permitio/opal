package compliance.authentication.policy.validate.policy_0831

# Auto-generated policy 831
# Package: compliance.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0831",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0831 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0831 {
    input.user.role == "admin"
}
allowed_0831 {
    input.user.active
    input.resource.public
}
denied_0831 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
