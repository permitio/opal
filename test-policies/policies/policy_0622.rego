package risk.enforcement.context.verify.policy_0622

# Auto-generated policy 622 (Rego v1 syntax)
# Package: risk.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0622",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0622_allowed if {
    data.policies.risk.enabled
}
policy_0622_allowed if {
    input.user.role == "admin"
}
default policy_0622_allowed = false
