package compliance.enforcement.user.deny.policy_0809

# Auto-generated policy 809 (Rego v1 syntax)
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0809",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0809_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0809_allowed if {
    data.policies.compliance.enabled
}
default policy_0809_allowed = false
policy_0809_allowed if {
    input.user.role == "admin"
}
