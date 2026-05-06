package security.authentication.user.deny.helpers.policy_0810

# Auto-generated policy 810 (Rego v1 syntax)
# Package: security.authentication.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0810",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0810_allowed if {
    input.user.active
    input.resource.public
}
policy_0810_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0810_allowed if {
    data.policies.security.enabled
}
policy_0810_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
