package compliance.validation.context.check.policy_0881

# Auto-generated policy 881
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0881",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0881 {
    input.user.active
    input.resource.public
}
approved_0881 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0881 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
