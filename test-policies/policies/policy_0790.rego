package audit.authentication.context.check.policy_0790

# Auto-generated policy 790
# Package: audit.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0790",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0790 {
    input.user.role == "admin"
}
approved_0790 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0790 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
