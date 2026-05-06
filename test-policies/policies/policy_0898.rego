package security.enforcement.policy.allow.policy_0898

# Auto-generated policy 898 (Rego v1 syntax)
# Package: security.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0898",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0898_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0898_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0898_allowed = false
