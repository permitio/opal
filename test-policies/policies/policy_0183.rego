package compliance.authentication.policy.check.utils.policy_0183

# Auto-generated policy 183 (Rego v1 syntax)
# Package: compliance.authentication.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0183",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0183_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0183_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0183_allowed = false
