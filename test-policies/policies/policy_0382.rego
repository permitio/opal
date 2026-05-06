package access.authentication.policy.validate.data.policy_0382

# Auto-generated policy 382
# Package: access.authentication.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0382",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0382 {
    data.policies.access.enabled
}
allowed_0382 {
    input.user.active
    input.resource.public
}

# Utility function for user info
