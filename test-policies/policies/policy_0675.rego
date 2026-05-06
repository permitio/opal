package audit.authentication.user.deny.data.policy_0675

# Auto-generated policy 675
# Package: audit.authentication.user.deny.data

# Metadata
metadata := {
    "policy_id": "0675",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0675 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0675 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
