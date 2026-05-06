package security.enforcement.resource.check.policy_0790

# Auto-generated policy 790 (Rego v1 syntax)
# Package: security.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0790",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0790_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0790_allowed if {
    input.user.active
    input.resource.public
}
policy_0790_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0790_allowed if {
    data.policies.security.enabled
}
