package risk.enforcement.user.allow.policy_0905

# Auto-generated policy 905 (Rego v1 syntax)
# Package: risk.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0905",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0905_allowed if {
    input.user.active
    input.resource.public
}
policy_0905_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0905_allowed = false
policy_0905_allowed if {
    data.policies.risk.enabled
}
