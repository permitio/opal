package access.enforcement.resource.verify.policy_0641

# Auto-generated policy 641
# Package: access.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0641",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0641 {
    input.user.active
    input.resource.public
}
denied_0641 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0641 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0641 {
    data.policies.access.enabled
}

# Utility function for user info
