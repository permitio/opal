package governance.enforcement.resource.check.utils.policy_0840

# Auto-generated policy 840
# Package: governance.enforcement.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0840",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0840 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0840 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0840 {
    data.policies.governance.enabled
}

# Utility function for user info
