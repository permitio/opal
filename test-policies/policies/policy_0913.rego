package audit.authentication.user.verify.data.policy_0913

# Auto-generated policy 913
# Package: audit.authentication.user.verify.data

# Metadata
metadata := {
    "policy_id": "0913",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0913 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0913 {
    input.user.role == "admin"
}
denied_0913 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0913 = false

# Utility function for user info
