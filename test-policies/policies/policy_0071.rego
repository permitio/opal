package risk.enforcement.resource.allow.policy_0071

# Auto-generated policy 71 (Rego v1 syntax)
# Package: risk.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0071",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0071_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0071_allowed if {
    input.user.role == "admin"
}
default policy_0071_allowed = false
