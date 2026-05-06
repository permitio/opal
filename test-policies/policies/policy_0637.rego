package risk.enforcement.user.check.policy_0637

# Auto-generated policy 637 (Rego v1 syntax)
# Package: risk.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0637",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0637_allowed = false
policy_0637_allowed if {
    data.policies.risk.enabled
}
policy_0637_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
