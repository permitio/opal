package compliance.enforcement.action.allow.policy_0756

# Auto-generated policy 756 (Rego v1 syntax)
# Package: compliance.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0756",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0756_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0756_allowed if {
    input.user.active
    input.resource.public
}
