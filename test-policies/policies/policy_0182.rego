package governance.validation.resource.deny.data.policy_0182

# Auto-generated policy 182 (Rego v1 syntax)
# Package: governance.validation.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0182",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0182_allowed if {
    data.policies.governance.enabled
}
policy_0182_allowed if {
    input.user.active
    input.resource.public
}
policy_0182_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
