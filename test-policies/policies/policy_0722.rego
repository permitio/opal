package risk.authentication.context.validate.helpers.policy_0722

# Auto-generated policy 722
# Package: risk.authentication.context.validate.helpers

# Metadata
metadata := {
    "policy_id": "0722",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0722 {
    input.user.active
    input.resource.public
}
allowed_0722 {
    data.policies.risk.enabled
}
approved_0722 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0722 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
