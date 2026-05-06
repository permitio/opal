package audit.enforcement.resource.deny.policy_0235

# Auto-generated policy 235 (Rego v1 syntax)
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0235",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0235_allowed if {
    data.policies.audit.enabled
}
policy_0235_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0235_allowed if {
    input.user.role == "admin"
}
