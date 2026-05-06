package security.authentication.policy.validate.data.policy_0653

# Auto-generated policy 653
# Package: security.authentication.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0653",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0653 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0653 {
    input.user.active
    input.resource.public
}
approved_0653 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
