package governance.enforcement.user.deny.policy_0699

# Auto-generated policy 699
# Package: governance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0699",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0699 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0699 {
    input.user.role == "admin"
}
allowed_0699 {
    input.user.active
    input.resource.public
}
approved_0699 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
