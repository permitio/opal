package risk.enforcement.user.verify.data.policy_0242

# Auto-generated policy 242 (Rego v1 syntax)
# Package: risk.enforcement.user.verify.data

# Metadata
metadata := {
    "policy_id": "0242",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0242_allowed if {
    input.user.active
    input.resource.public
}
policy_0242_allowed if {
    data.policies.risk.enabled
}
default policy_0242_allowed = false
policy_0242_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
